"""BodyMind A351 private athlete photo albums and personal film.

Privacy invariants:
* All requests resolve the athlete from the existing unguessable online_token
  in the original tesserati SQLite database; never from submitted athlete ID.
* Every album file is stored outside Flask static under /data, always scoped to
  the authenticated athlete, and is served by authorization-checked endpoints.
* Uploaded images are decoded and rewritten as JPEG without EXIF/GPS metadata.
* No public links, external services, face detection or background publishing.
* The legacy administrative DB is opened strictly read-only.
"""
import hashlib
import hmac
import io
import os
import re
import shutil
import secrets
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import abort, jsonify, make_response, redirect, render_template_string, request, send_file
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT=Path('/data/tenants/default/private_gallery_a351')
MAX_IMAGE_BYTES=10*1024*1024
MAX_PIXELS=16000000
MAX_PHOTOS=24
MIN_FREE_BYTES=256*1024*1024
MAX_FILM_PHOTOS=8
Image.MAX_IMAGE_PIXELS=MAX_PIXELS

def _no_cache(response):
    response.headers['Cache-Control']='private, no-store, max-age=0'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

def _owner(db_provider,token):
    if not re.fullmatch(r'[A-Za-z0-9_\-]{12,180}',token or ''):
        abort(404)
    db=db_provider()
    try:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT id FROM tesserati WHERE online_token=?',(token,)).fetchone()
    finally:
        db.close()
    if not row:abort(404)
    return int(row['id'])

def _safe_dir(owner):
    path=ROOT/str(owner)
    if path.exists() and (path.is_symlink() or not path.is_dir()):abort(500)
    return path

def _open_album(owner,create=False):
    if not create and not (ROOT/'albums.sqlite3').is_file():
        return None
    if ROOT.is_symlink():abort(500)
    if create:
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    d=sqlite3.connect(str(ROOT/'albums.sqlite3'),timeout=15)
    d.row_factory=sqlite3.Row
    if create:
        d.execute('PRAGMA busy_timeout=15000')
        d.execute("""CREATE TABLE IF NOT EXISTS photos(
           id TEXT PRIMARY KEY,athlete_id INTEGER NOT NULL,
           filename TEXT NOT NULL,created_at TEXT NOT NULL,
           caption TEXT DEFAULT '')""")
        d.execute("""CREATE INDEX IF NOT EXISTS album_owner_idx
                     ON photos(athlete_id,created_at)""")
        d.execute("""CREATE TABLE IF NOT EXISTS films(
           athlete_id INTEGER PRIMARY KEY,
           filename TEXT NOT NULL,
           content_sig TEXT NOT NULL,
           created_at TEXT NOT NULL)""")
        d.commit()
    return d

def _photos(owner):
    db=_open_album(owner)
    if db is None:return []
    try:
        return db.execute('SELECT id,filename,caption,created_at FROM photos WHERE athlete_id=? ORDER BY created_at,id',(owner,)).fetchall()
    finally:db.close()

def _csrf(app,token):
    serializer=URLSafeTimedSerializer(str(app.secret_key),salt='a351-private-gallery-post')
    return serializer.dumps({'owner':hashlib.sha256(token.encode()).hexdigest()[:24]})

def _verify_post(app,token):
    raw=request.form.get('csrf','')
    try:payload=URLSafeTimedSerializer(str(app.secret_key),salt='a351-private-gallery-post').loads(raw,max_age=3600)
    except (BadSignature,SignatureExpired):abort(403)
    if not hmac.compare_digest(payload.get('owner',''),hashlib.sha256(token.encode()).hexdigest()[:24]):
        abort(403)
    origin=request.headers.get('Origin')
    if origin:
        uri=urlparse(origin)
        if uri.scheme!='https' or uri.netloc.lower()!=request.host.lower():abort(403)
    if request.content_length and request.content_length>MAX_IMAGE_BYTES*5+65536:abort(413)

def _normalize_image(data):
    if not data or len(data)>MAX_IMAGE_BYTES:abort(413)
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ('JPEG','PNG','WEBP'):abort(415)
            im.load()
            if im.width*im.height>MAX_PIXELS:abort(413)
            im=ImageOps.exif_transpose(im)
            im.thumbnail((1800,2400),Image.Resampling.LANCZOS)
            if im.mode not in ('RGB','RGBA'):
                im=im.convert('RGBA')
            if im.mode=='RGBA':
                bg=Image.new('RGB',im.size,(246,247,241))
                bg.paste(im,mask=im.getchannel('A'))
                im=bg
            else:im=im.convert('RGB')
            output=io.BytesIO()
            im.save(output,'JPEG',quality=85,optimize=True,progressive=True)
            return output.getvalue()
    except (OSError,ValueError,UnidentifiedImageError):
        abort(415)

def _film_manifest(rows):
    return hashlib.sha256('|'.join(r['id'] for r in rows[:MAX_FILM_PHOTOS]).encode()).hexdigest()

def _build_film(owner,rows):
    if not rows:abort(400)
    if not Path('/usr/bin/ffmpeg').is_file():abort(503)
    dest=_safe_dir(owner)
    dest.mkdir(parents=True,exist_ok=True,mode=0o700)
    if shutil.disk_usage(dest).free<MIN_FREE_BYTES:abort(507)
    limited=rows[:MAX_FILM_PHOTOS]
    inputs=[]
    filters=[]
    for i,row in enumerate(limited):
        media=dest/row['filename']
        if not media.is_file() or media.is_symlink():abort(500)
        inputs+=['-loop','1','-t','3.2','-i',str(media)]
        filters.append(f'[{i}:v]fps=12,scale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]')
    if len(limited)==1:
        last='v0'
    else:
        last='v0'
        for i in range(1,len(limited)):
            target=f'f{i}'
            filters.append(f'[{last}][v{i}]xfade=transition=fade:duration=0.6:offset={2.6*i:.1f}[{target}]')
            last=target
    final=dest/('film_'+secrets.token_hex(14)+'.mp4')
    fd,tmp=tempfile.mkstemp(prefix='.render_',suffix='.mp4',dir=dest)
    os.close(fd)
    args=['/usr/bin/ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-threads','1']+inputs+[
        '-filter_complex',';'.join(filters),'-map',f'[{last}]',
        '-t',str(round(2.6*len(limited)+0.6,1)),
        '-an','-c:v','libx264','-preset','ultrafast','-crf','27',
        '-pix_fmt','yuv420p','-movflags','+faststart',tmp]
    try:
        subprocess.run(args,timeout=110,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        if not Path(tmp).is_file() or Path(tmp).stat().st_size<3000:abort(500)
        os.replace(tmp,final)
        return final
    except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
        abort(503)
    finally:
        try:Path(tmp).unlink(missing_ok=True)
        except OSError:pass

TEMPLATE=r"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="referrer" content="no-referrer">
<title>Le mie foto · BodyMind</title>
<style>
:root{color-scheme:dark;font-family:Manrope,system-ui,sans-serif;color:#f6fbf5;background:#0c2c3b}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(ellipse at 80% 15%,#3a6870,#0b2b3a 70%);min-height:100vh}
main{max-width:1050px;margin:auto;padding:clamp(20px,5vw,45px);padding-bottom:70px}
h1{font:normal clamp(37px,6vw,70px)/1.07 Georgia,serif;letter-spacing:-.035em;margin:6px 0 12px}
h2{font:normal 28px/1.2 Georgia,serif}
p{line-height:1.6;color:#e4f3ee}
a{color:#b8f1df}
.top{display:flex;flex-wrap:wrap;align-items:center;gap:15px;justify-content:space-between}
.card{padding:clamp(20px,4vw,28px);border-radius:24px;margin:22px 0;background:rgba(10,43,54,.79);border:1px solid rgba(184,231,210,.39)}
button,.button{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:12px 19px;border-radius:100px;border:1px solid #dff7e8;background:linear-gradient(125deg,#b3e8da,#fbd3b4);color:#14313a;font-weight:800;text-decoration:none;cursor:pointer}
button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #ffd6b2;outline-offset:3px}
input[type=file]{display:block;width:100%;padding:15px;margin-block:12px;border:1px dashed #aacfc5;border-radius:18px;color:#eff9f5}
label.check{display:flex;gap:12px;align-items:flex-start;margin:20px 0;line-height:1.5}
label.check input{width:20px;height:20px;flex-shrink:0}
.filmstrip{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;gap:18px;padding:18px 8px 25px}
.frame{position:relative;flex:0 0 clamp(185px,41vw,260px);scroll-snap-align:start;margin:9px 0;border:1px solid #9fcbbd;border-radius:16px;background:#103643}
.frame:before,.frame:after{content:"";position:absolute;left:8px;right:8px;height:9px;background:repeating-linear-gradient(90deg,#a9d7cc 0 9px,transparent 9px 20px)}
.frame:before{top:-11px}.frame:after{bottom:-11px}
.frame img{display:block;width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:15px 15px 0 0}
.frame footer{padding:13px;font-size:12px;color:#e8f1ed}
.frame button{min-height:40px;padding:8px 11px;font-size:12px}
video{display:block;width:min(100%,340px);max-height:560px;aspect-ratio:9/16;object-fit:contain;border-radius:24px;background:#061a26}
small{color:#d5eae4}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style></head><body><main>
<div class="top"><span>BODYMIND · LA MIA STORIA</span><a href="{{ home }}">Torna alla mia Home</a></div>
<h1>Il mio volo,<br>i miei ricordi.</h1>
<p>Il tuo album è privato. Le foto e il film non vengono pubblicati sul sito o sui social.</p>
<section class="card"><h2>Le mie foto</h2>
<p>Carica fino a 4 foto alla volta (JPG, PNG o WebP, massimo 10 MB ciascuna). Limite album: 24 fotografie.</p>
<form method="post" action="{{ upload }}" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{ csrf }}">
<input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple required>
<label class="check"><input type="checkbox" name="privacy" value="yes" required>
<span>Confermo di essere la persona autorizzata a gestire queste fotografie. Se raffigurano una minorenne, confermo di essere il genitore o tutore autorizzato. Le immagini restano nell'area privata.</span></label>
<button type="submit">Aggiungi al mio album</button>
</form></section>
<section class="card"><h2>La mia pellicola</h2>
{% if photos %}
<div class="filmstrip" aria-label="Le mie fotografie">
{% for item in photos %}
<article class="frame"><img src="{{ item.url }}" alt="Foto personale {{ loop.index }}" loading="lazy">
<footer>Ricordo {{ loop.index }}<form action="{{ item.delete }}" method="post">
<input type="hidden" name="csrf" value="{{ csrf }}"><button type="submit">Elimina foto</button>
</form></footer></article>
{% endfor %}</div>
{% else %}<p>Ancora nessuna fotografia: comincia caricando le immagini che preferisci.</p>{% endif %}
</section>
<section class="card"><h2>Il mio film personale</h2>
<p>Scegli «Crea il mio film» per montare fino a otto delle tue foto con dissolvenze. Non viene inviato a servizi esterni.</p>
{% if film %}<video controls playsinline preload="none" src="{{ film }}" aria-label="Film personale dell'atleta"></video>
<p><small>Il film sarà visibile solo da quest'area e diventerà la copertina della tua Home personale.</small></p>{% endif %}
{% if photos %}<form method="post" action="{{ generate }}">
<input type="hidden" name="csrf" value="{{ csrf }}">
<button type="submit">Crea il mio film</button></form>{% endif %}
</section>
</main></body></html>"""

def install_family_gallery(app,db_provider):
    """Register private token routes. No album table/file is made at app boot."""
    if 'a351_album_home' in app.view_functions:return

    base='/app-tesserato/<token>/album'

    def home(token):
        owner=_owner(db_provider,token)
        rows=_photos(owner)
        db=_open_album(owner)
        film=None
        if db:
            try:
                existing=db.execute('SELECT filename FROM films WHERE athlete_id=?',(owner,)).fetchone()
                if existing:
                    target=_safe_dir(owner)/existing['filename']
                    if target.is_file() and not target.is_symlink():
                        film=f'/app-tesserato/{token}/album/film'
            finally:db.close()
        p=[{'url':f'/app-tesserato/{token}/album/photo/{x["id"]}',
            'delete':f'/app-tesserato/{token}/album/delete/{x["id"]}'} for x in rows]
        page=render_template_string(TEMPLATE,home=f'/app-tesserato/{token}',
          upload=f'/app-tesserato/{token}/album/upload',photos=p,csrf=_csrf(app,token),
          film=film,generate=f'/app-tesserato/{token}/album/generate')
        return _no_cache(make_response(page))

    def upload(token):
        owner=_owner(db_provider,token)
        _verify_post(app,token)
        if request.form.get('privacy')!='yes':abort(400)
        if shutil.disk_usage(ROOT.parent).free<MIN_FREE_BYTES:abort(507)
        files=request.files.getlist('photos')
        if not files or len(files)>4:abort(400)
        items=[_normalize_image(f.read(MAX_IMAGE_BYTES+1)) for f in files]
        db=_open_album(owner,create=True)
        target=_safe_dir(owner);target.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            oldfilm=db.execute('SELECT filename FROM films WHERE athlete_id=?',(owner,)).fetchone()
            total=db.execute('SELECT COUNT(*) FROM photos WHERE athlete_id=?',(owner,)).fetchone()[0]
            if total+len(items)>MAX_PHOTOS:abort(413)
            written=[]
            try:
                for image in items:
                    photoid=secrets.token_hex(15)
                    name=photoid+'.jpg'
                    fn=target/name
                    with open(fn,'xb') as fh:fh.write(image)
                    os.chmod(fn,0o600)
                    written.append(fn)
                    db.execute('INSERT INTO photos(id,athlete_id,filename,created_at) VALUES(?,?,?,?)',
                      (photoid,owner,name,datetime.now(timezone.utc).isoformat()))
                db.execute('DELETE FROM films WHERE athlete_id=?',(owner,))
                db.commit()
                if oldfilm:
                    previous=target/oldfilm['filename']
                    if previous.is_file() and not previous.is_symlink():previous.unlink()
            except Exception:
                db.rollback()
                for fn in written:fn.unlink(missing_ok=True)
                raise
        finally:db.close()
        return _no_cache(redirect(f'/app-tesserato/{token}/album',code=303))

    def photo(token,photoid):
        owner=_owner(db_provider,token)
        if not re.fullmatch(r'[0-9a-f]{30}',photoid):abort(404)
        db=_open_album(owner)
        if db is None:abort(404)
        try:
            row=db.execute('SELECT filename FROM photos WHERE id=? AND athlete_id=?',(photoid,owner)).fetchone()
        finally:db.close()
        if not row:abort(404)
        target=_safe_dir(owner)/row['filename']
        if not target.is_file() or target.is_symlink():abort(404)
        return _no_cache(send_file(target,mimetype='image/jpeg',conditional=False))

    def delete(token,photoid):
        owner=_owner(db_provider,token);_verify_post(app,token)
        db=_open_album(owner)
        if db is None:abort(404)
        try:
            row=db.execute('SELECT filename FROM photos WHERE id=? AND athlete_id=?',(photoid,owner)).fetchone()
            if not row:abort(404)
            oldfilm=db.execute('SELECT filename FROM films WHERE athlete_id=?',(owner,)).fetchone()
            db.execute('DELETE FROM photos WHERE id=? AND athlete_id=?',(photoid,owner))
            db.execute('DELETE FROM films WHERE athlete_id=?',(owner,))
            db.commit()
        finally:db.close()
        path=_safe_dir(owner)/row['filename']
        if path.is_file() and not path.is_symlink():path.unlink()
        if oldfilm:
            stale=_safe_dir(owner)/oldfilm['filename']
            if stale.is_file() and not stale.is_symlink():stale.unlink()
        return _no_cache(redirect(f'/app-tesserato/{token}/album',code=303))

    def generate(token):
        owner=_owner(db_provider,token);_verify_post(app,token)
        rows=_photos(owner)
        if not rows:abort(400)
        result=_build_film(owner,rows)
        db=_open_album(owner,create=True)
        try:
            old=db.execute('SELECT filename FROM films WHERE athlete_id=?',(owner,)).fetchone()
            db.execute('INSERT OR REPLACE INTO films(athlete_id,filename,content_sig,created_at) VALUES(?,?,?,?)',
               (owner,result.name,_film_manifest(rows),datetime.now(timezone.utc).isoformat()))
            db.commit()
            if old:
                previous=_safe_dir(owner)/old['filename']
                if previous!=result and previous.is_file() and not previous.is_symlink():previous.unlink()
        finally:db.close()
        return _no_cache(redirect(f'/app-tesserato/{token}/album',code=303))

    def film(token):
        owner=_owner(db_provider,token)
        db=_open_album(owner)
        if db is None:abort(404)
        try:row=db.execute('SELECT filename FROM films WHERE athlete_id=?',(owner,)).fetchone()
        finally:db.close()
        if not row:abort(404)
        target=_safe_dir(owner)/row['filename']
        if not target.is_file() or target.is_symlink():abort(404)
        return _no_cache(send_file(target,mimetype='video/mp4',conditional=True))

    def status(token):
        owner=_owner(db_provider,token)
        db=_open_album(owner)
        present=False
        if db:
            try:
                row=db.execute('SELECT filename FROM films WHERE athlete_id=?',(owner,)).fetchone()
                present=bool(row and (_safe_dir(owner)/row['filename']).is_file())
            finally:db.close()
        return _no_cache(jsonify({'available':present,'url':f'/app-tesserato/{token}/album/film' if present else None}))

    rules=[
      (base,'a351_album_home',home,['GET']),
      (base+'/upload','a351_album_upload',upload,['POST']),
      (base+'/photo/<photoid>','a351_album_photo',photo,['GET']),
      (base+'/delete/<photoid>','a351_album_delete',delete,['POST']),
      (base+'/generate','a351_album_generate',generate,['POST']),
      (base+'/film','a351_album_film',film,['GET']),
      (base+'/status','a351_album_status',status,['GET']),
    ]
    for url,endpoint,handler,methods in rules:
        app.add_url_rule(url,endpoint,handler,methods=methods)
