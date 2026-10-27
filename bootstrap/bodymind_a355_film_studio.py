"""BodyMind A355 — private family film studio.

Adds a carefully bounded local FFmpeg editor atop the A351 consented,
token-scoped photo album. No external AI/image provider and no public gallery.
The administrative SQLite database is never written.
"""
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from flask import abort, jsonify, make_response, redirect, render_template_string, request, send_file

MAX_SELECTED=8
MAX_AUDIO_BYTES=12*1024*1024
MIN_FREE=512*1024*1024
DAILY_RENDERS=6
FRAME_W=480
FRAME_H=854
FPS=12
TRANSITION=.65
BEAT_STEP=240/86
ALLOWED_STYLES={'aurora','eden','stardust'}
AUDIO_FORMATS={'mp3','wav','m4a','aac','ogg','flac'}
FONT=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')

def _safe_title(raw):
    title=(raw or '').strip()
    if not 1<=len(title)<=44 or any(ord(c)<32 or c in '<>{}\\/' for c in title):
        abort(400,'Titolo non valido: inserisci da 1 a 44 caratteri.')
    return title

def _access(album,db_provider,token):
    return album._owner(db_provider,token)

def _db(album,owner,create=False):
    db=album._open_album(owner,create=create)
    if db is None:return None
    if create:
        db.execute("""CREATE TABLE IF NOT EXISTS studio_films(
            athlete_id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            title TEXT NOT NULL,
            style TEXT NOT NULL,
            music TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS studio_events(
            athlete_id INTEGER NOT NULL,
            created_at TEXT NOT NULL)""")
        db.execute("""CREATE INDEX IF NOT EXISTS studio_events_owner
                      ON studio_events(athlete_id,created_at)""")
        db.commit()
    return db

def _film_row(album,owner):
    db=_db(album,owner)
    if db is None:return None
    try:
        try:return db.execute('SELECT filename,title,style,music,created_at FROM studio_films WHERE athlete_id=?',(owner,)).fetchone()
        except sqlite3.OperationalError:return None
    finally:db.close()

def _owner_path(album,owner):
    folder=album._safe_dir(owner)
    if folder.is_symlink():abort(500)
    return folder

def _verified_photos(album,owner,identifiers):
    if not 1<=len(identifiers)<=MAX_SELECTED or len(set(identifiers))!=len(identifiers):
        abort(400,'Seleziona da 1 a 8 fotografie distinte.')
    if any(not re.fullmatch(r'[0-9a-f]{30}',i or '') for i in identifiers):
        abort(400)
    available={row['id']:row for row in album._photos(owner)}
    directory=_owner_path(album,owner)
    files=[]
    for identifier in identifiers:
        if identifier not in available:abort(404)
        filename=available[identifier]['filename']
        if not re.fullmatch(r'[0-9a-f]{30}\.jpg',filename):
            abort(400)
        path=directory/filename
        if not path.is_file() or path.is_symlink():abort(404)
        files.append(path)
    return files

def _original_music(path,duration,style):
    """Locally composed instrumental motifs — no licensed third-party samples."""
    profiles={
        'aurora':([220,174.61,261.63,196],[329.63,392,440,392,349.23,329.63,293.66,261.63]),
        'eden':([174.61,196,220,164.81],[261.63,293.66,329.63,392,349.23,329.63,261.63,293.66]),
        'stardust':([164.81,220,196,174.61],[392,440,493.88,440,392,349.23,329.63,392]),
    }
    roots,melody=profiles[style]
    rate=22050
    total=int(duration*rate)
    amplitude=.68
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        batch=bytearray()
        for i in range(total):
            t=i/rate
            phrase=int(t/BEAT_STEP)
            root=roots[phrase%len(roots)]
            beat=t/(BEAT_STEP/4)
            note=melody[int(beat)%len(melody)]
            position=(t%(BEAT_STEP/4))/(BEAT_STEP/4)
            bell=math.sin(2*math.pi*note*t)*math.exp(-4.0*position)
            pad=(.46*math.sin(2*math.pi*root*t)+
                 .20*math.sin(2*math.pi*(root*1.5)*t)+
                 .12*math.sin(2*math.pi*(root*2)*t))
            breathe=.76+.15*math.sin(2*math.pi*.16*t)
            fade=min(1,t/1.7,max(0,(duration-t)/2.2))
            sample=max(-1,min(1,(pad*.32+bell*.17)*fade*breathe*amplitude))
            batch+=struct.pack('<h',int(sample*32767))
            if len(batch)>131072:
                w.writeframesraw(batch);batch.clear()
        if batch:w.writeframesraw(batch)

def _probe_audio(path):
    command=['/usr/bin/ffprobe','-v','error','-show_entries',
             'format=duration:stream=codec_type','-of','json',str(path)]
    try:
        result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              timeout=12,check=True)
        payload=json.loads(result.stdout)
        duration=float(payload.get('format',{}).get('duration',0))
        if not 3<=duration<=600 or not any(s.get('codec_type')=='audio' for s in payload.get('streams',[])):
            abort(415,'Il file deve contenere una traccia audio valida.')
    except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError,
            ValueError,KeyError,TypeError):
        abort(415,'Formato audio non riconosciuto.')

def _render(album,owner,files,title,style,audio_bytes=None,audio_suffix=None):
    if not Path('/usr/bin/ffmpeg').is_file() or not FONT.is_file():
        abort(503,'Motore video non disponibile.')
    folder=_owner_path(album,owner)
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if shutil.disk_usage(folder).free<MIN_FREE:abort(507,'Spazio di elaborazione insufficiente.')
    duration=BEAT_STEP*len(files)+TRANSITION
    with tempfile.TemporaryDirectory(prefix='.studio_work_',dir=folder) as wd:
        work=Path(wd)
        headline=work/'headline.txt'
        headline.write_text(title+' in volo',encoding='utf-8')
        byline=work/'byline.txt'
        byline.write_text('BODYMIND  |  IL MIO PERCORSO',encoding='utf-8')
        if audio_bytes is None:
            track=work/'originale.wav'
            _original_music(track,duration,style)
        else:
            track=work/('musica.'+audio_suffix)
            with open(track,'xb') as out:out.write(audio_bytes)
            _probe_audio(track)
        args=['/usr/bin/ffmpeg','-hide_banner','-loglevel','error',
              '-nostdin','-y','-filter_complex_threads','1']
        for path in files:
            args+=['-loop','1','-framerate',str(FPS),'-t',str(BEAT_STEP+TRANSITION),
                   '-i',str(path)]
        args+=['-stream_loop','-1','-i',str(track)]
        filters=[]
        for i in range(len(files)):
            filters.append(
               f'[{i}:v]fps={FPS},scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=increase,'
               f'crop={FRAME_W}:{FRAME_H},setsar=1,settb=AVTB,format=yuv420p,'
               f'setpts=PTS-STARTPTS[v{i}]')
        last='v0'
        transitions=('fade','smoothleft','smoothup','dissolve','circleopen')
        for i in range(1,len(files)):
            output=f'mix{i}'
            filters.append(f'[{last}][v{i}]xfade=transition={transitions[(i-1)%len(transitions)]}:'
                           f'duration={TRANSITION}:offset={BEAT_STEP*i:.5f}[{output}]')
            last=output
        # Explicit textfile avoids FFmpeg filter injection from family-supplied titles.
        filters.append(
            f'[{last}]drawtext=fontfile={FONT}:textfile={headline}:expansion=none:'
            f'fontcolor=white:fontsize=36:x=(w-text_w)/2:y=h*0.77:'
            f'box=1:boxcolor=0x07182799:boxborderw=16:enable=lt(t\,4.2)[intro]')
        filters.append(
            f'[intro]drawtext=fontfile={FONT}:textfile={byline}:expansion=none:'
            f'fontcolor=0xffe5c6:fontsize=18:x=(w-text_w)/2:y=h*0.88:'
            f'enable=gte(t\,0)[output]')
        filters.append(
            f'[{len(files)}:a]aresample=44100,volume=0.72,'
            f'afade=t=in:st=0:d=1.1,'
            f'afade=t=out:st={max(0,duration-2.0):.2f}:d=1.9[aout]')
        temp=work/'cinema.mp4'
        cmd=args+['-filter_complex',';'.join(filters),'-map','[output]','-map','[aout]',
                  '-t',f'{duration:.3f}','-c:v','libx264','-preset','ultrafast',
                  '-crf','26','-pix_fmt','yuv420p','-r',str(FPS),
                  '-c:a','aac','-b:a','112k','-ac','2',
                  '-movflags','+faststart',str(temp)]
        try:
            subprocess.run(cmd,timeout=140,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
        except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError):
            abort(503,'Montaggio non riuscito. Le tue foto sono intatte.')
        if not temp.is_file() or temp.stat().st_size<8000:
            abort(503,'Film non disponibile.')
        dest=folder/('studio_'+secrets.token_hex(14)+'.mp4')
        os.replace(temp,dest)
        os.chmod(dest,0o600)
        return dest

STUDIO_TEMPLATE=r"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive"><meta name="referrer" content="no-referrer">
<title>Il mio film · BodyMind</title>
<style>
:root{font-family:Manrope,system-ui,sans-serif;color:#f9fbf6;background:#071822}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:
 radial-gradient(ellipse 85% 35% at 8% 12%,rgba(74,161,158,.35),transparent 80%),
 radial-gradient(ellipse 80% 45% at 98% 68%,rgba(184,119,175,.24),transparent 85%),
 linear-gradient(#071822,#102c37 60%,#071822)}
main{max-width:1000px;margin:0 auto;padding:clamp(18px,5vw,48px);padding-bottom:70px}
header{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
h1{font:normal clamp(38px,7vw,74px)/1.02 Georgia,serif;letter-spacing:-.04em;margin:24px 0}
h2{font:normal clamp(24px,4vw,33px)/1.16 Georgia,serif}
p{line-height:1.65;color:#e2f1eb}small{color:#d3e4df}
a{color:#c0f1e4}
.card{padding:clamp(17px,4vw,29px);background:rgba(13,39,52,.81);border:1px solid rgba(181,225,212,.37);border-radius:24px;margin:23px 0}
label,.label{display:block;font-weight:750;margin:12px 0 7px}
input[type=text],select,input[type=file]{display:block;width:100%;min-height:47px;background:#102c38;color:white;border:1px solid #7abbb0;border-radius:13px;padding:13px;margin-bottom:17px;font:inherit}
button,.button{display:inline-flex;justify-content:center;align-items:center;border:1px solid #dcf2e7;border-radius:99px;padding:12px 20px;min-height:48px;color:#0a3540;background:linear-gradient(105deg,#b6f3df,#f8d4b7);font-weight:800;cursor:pointer;text-decoration:none}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #ffdfb9;outline-offset:3px}
.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:12px}
.gallery label{position:relative;margin:0;background:#102e3b;border-radius:15px;overflow:hidden;border:1px solid #70a69f;cursor:pointer}
.gallery img{display:block;width:100%;height:165px;object-fit:cover}
.gallery span{position:absolute;top:7px;left:7px;padding:6px 8px;background:#082837d9;border-radius:9px;font-size:13px}
.gallery input{accent-color:#d6eccc;width:20px;height:20px;vertical-align:middle}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:17px}
video{display:block;max-width:100%;width:min(100%,340px);max-height:610px;aspect-ratio:480/854;object-fit:contain;border-radius:16px;background:#020e17}
.notice{border-left:3px solid #f5cfaa;padding-left:15px}
details{margin:20px 0}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important}}
</style></head><body><main>
<header><span>BODYMIND · I MIEI MOMENTI IN VOLO</span>
<a href="{{ album_url }}">← Torna al mio album</a></header>
<h1>La magia del<br><i>mio volo.</i></h1>
<p>Le tue fotografie diventano un film personale, con titolo, transizioni cinematografiche e musica sincronizzata. Solo nella tua area privata.</p>
{% if film %}
<section class="card"><h2>Il tuo film è pronto</h2>
<video controls playsinline preload="metadata" src="{{ film_url }}" aria-label="Il mio film BodyMind"></video>
<p><strong>{{ film.title }}</strong> · {{ film.style }} · {{ film.created_at[:10] }}</p>
<a class="button" href="{{ download_url }}">Scarica MP4</a>
<form method="post" action="{{ delete_url }}" style="margin-top:18px">
<input type="hidden" name="csrf" value="{{ csrf }}">
<button type="submit">Elimina soltanto il film</button>
</form></section>{% endif %}
<section class="card"><h2>Regista per un giorno</h2>
{% if photos %}
<form action="{{ render_url }}" method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{ csrf }}">
<p>Seleziona fino a otto foto. L'ordine scelto segue l'ordine dell'album; ogni passaggio è calibrato sul ritmo musicale.</p>
<div class="gallery">
{% for item in photos %}
<label><img src="{{ item.url }}" alt="Ricordo {{ loop.index }}" loading="lazy">
<span><input type="checkbox" name="photos" value="{{ item.id }}" {% if loop.index<=6 %}checked{% endif %}> {{ loop.index }}</span></label>
{% endfor %}</div>
<label for="title">Nome o titolo dell'atleta</label>
<input id="title" type="text" name="title" required minlength="1" maxlength="44" value="{{ athlete_title }}">
<div class="row"><div>
<label for="style">Atmosfera del film</label>
<select id="style" name="style">
<option value="aurora">Aurora · dolce e luminosa</option>
<option value="eden">Eden · sognante e poetica</option>
<option value="stardust">Stardust · epica e stellare</option>
</select></div><div>
<label for="music">Colonna sonora</label>
<select id="music" name="music" onchange="document.getElementById('own-music').hidden=this.value!=='own'">
<option value="original">Musica originale BodyMind</option>
<option value="own">Carico un mio brano autorizzato</option>
</select></div></div>
<div id="own-music" hidden>
<label for="audio">Audio MP3, M4A, WAV, AAC, FLAC o OGG (max 12 MB)</label>
<input id="audio" name="audio" type="file" accept=".mp3,.m4a,.wav,.aac,.flac,.ogg,audio/*">
<label><input type="checkbox" name="rights" value="yes">
Dichiaro di possedere l'autorizzazione necessaria a utilizzare e sincronizzare questo brano nel film.</label>
</div>
<p><small>Durata indicativa: 3–23 secondi secondo il numero di foto. Il montaggio viene elaborato sul server e le foto non sono inviate a sistemi esterni.</small></p>
<button type="submit">Crea il mio film cinematografico</button>
</form>
{% else %}
<p>Prima carica qualche foto nel tuo album personale.</p>
<a class="button" href="{{ album_url }}">Aggiungi fotografie</a>
{% endif %}</section>
<section class="card"><h2>Un ricordo protetto</h2>
<p class="notice">Solo chi possiede il collegamento privato autorizzato della famiglia può visualizzare o scaricare il film. Verifica di avere il consenso a usare immagini di altri bambini. Il film non viene pubblicato sui social.</p>
<a href="{{ home_url }}">Torna alla mia Home</a></section>
</main></body></html>"""

def install_family_film_studio(app,db_provider,album):
    """Attach family-only routes to the existing, authorized A351 gallery."""
    if 'a355_studio_home' in app.view_functions:return
    if 'a351_album_home' not in app.view_functions:
        raise RuntimeError('A355 requires A351 family access controls')
    base='/app-tesserato/<token>/studio'
    # The album template is an existing user-visible page; no DB changes.
    marker='<section class="card"><h2>Il mio film personale</h2>'
    if marker in album.TEMPLATE and 'A355 FILM STUDIO' not in album.TEMPLATE:
        album.TEMPLATE=album.TEMPLATE.replace(
          marker,'<!-- A355 FILM STUDIO --><section class="card"><h2>Il mio cinema</h2>'
                 '<p>Crea il tuo video personale con titoli, musica e transizioni.</p>'
                 '<a class="button" href="/app-tesserato/{{ request.view_args.token }}/studio">Apri il mio studio</a>'
                 '</section>'+marker,1)

    def home(token):
        owner=_access(album,db_provider,token)
        rows=album._photos(owner)
        movie=_film_row(album,owner)
        found=bool(movie and re.fullmatch(r'studio_[0-9a-f]{28}\.mp4',movie['filename'])
                   and (_owner_path(album,owner)/movie['filename']).is_file())
        photos=[{'id':r['id'],'url':f'/app-tesserato/{token}/album/photo/{r["id"]}'} for r in rows]
        page=render_template_string(STUDIO_TEMPLATE,
            csrf=album._csrf(app,token),photos=photos,film=movie if found else None,
            athlete_title='Il mio viaggio',
            home_url=f'/app-tesserato/{token}',
            album_url=f'/app-tesserato/{token}/album',
            film_url=f'/app-tesserato/{token}/studio/film',
            download_url=f'/app-tesserato/{token}/studio/download',
            render_url=f'/app-tesserato/{token}/studio/render',
            delete_url=f'/app-tesserato/{token}/studio/delete')
        return album._no_cache(make_response(page))

    def render(token):
        owner=_access(album,db_provider,token)
        album._verify_post(app,token)
        if request.content_length and request.content_length>MAX_AUDIO_BYTES+240000:
            abort(413)
        style=request.form.get('style','aurora')
        if style not in ALLOWED_STYLES:abort(400)
        title=_safe_title(request.form.get('title'))
        files=_verified_photos(album,owner,request.form.getlist('photos'))
        music=request.form.get('music','original')
        if music not in ('original','own'):abort(400)
        audio_bytes=None
        audio_suffix=None
        if music=='own':
            if request.form.get('rights')!='yes':abort(400,'Conferma i diritti per la musica.')
            uploaded=request.files.get('audio')
            if not uploaded or not uploaded.filename:abort(400)
            audio_suffix=uploaded.filename.rsplit('.',1)[-1].lower()
            if audio_suffix not in AUDIO_FORMATS:abort(415)
            audio_bytes=uploaded.read(MAX_AUDIO_BYTES+1)
            if not audio_bytes or len(audio_bytes)>MAX_AUDIO_BYTES:abort(413)
        # Per-athlete nonblocking lock makes simultaneous renders safe.
        import fcntl
        folder=_owner_path(album,owner)
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        lockfile=folder/'.studio.lock'
        with open(lockfile,'a+b') as lock:
            os.chmod(lockfile,0o600)
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:abort(409,'Un altro montaggio è già in corso.')
            db=_db(album,owner,create=True)
            try:
                today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
                count=db.execute('SELECT COUNT(*) FROM studio_events WHERE athlete_id=? AND created_at>=?',
                                 (owner,today)).fetchone()[0]
                if count>=DAILY_RENDERS:abort(429,'Hai raggiunto il limite giornaliero di montaggi.')
                dest=_render(album,owner,files,title,style,audio_bytes,audio_suffix)
                old=db.execute('SELECT filename FROM studio_films WHERE athlete_id=?',(owner,)).fetchone()
                try:
                    db.execute('INSERT OR REPLACE INTO studio_films VALUES(?,?,?,?,?,?)',
                      (owner,dest.name,title,style,'personale' if music=='own' else 'originale',
                       datetime.now(timezone.utc).isoformat()))
                    db.execute('INSERT INTO studio_events VALUES (?,?)',
                      (owner,datetime.now(timezone.utc).isoformat()))
                    db.commit()
                except Exception:
                    db.rollback();dest.unlink(missing_ok=True);raise
                if old and old['filename']!=dest.name:
                    previous=folder/old['filename']
                    if previous.is_file() and not previous.is_symlink() and re.fullmatch(r'studio_[0-9a-f]{28}\.mp4',old['filename']):
                        previous.unlink()
            finally:db.close()
        return album._no_cache(redirect(f'/app-tesserato/{token}/studio',code=303))

    def media(token,download=False):
        owner=_access(album,db_provider,token)
        row=_film_row(album,owner)
        if not row or not re.fullmatch(r'studio_[0-9a-f]{28}\.mp4',row['filename']):abort(404)
        target=_owner_path(album,owner)/row['filename']
        if not target.is_file() or target.is_symlink():abort(404)
        return album._no_cache(send_file(target,mimetype='video/mp4',
            as_attachment=download,download_name='bodymind-il-mio-volo.mp4',
            conditional=not download))

    def erase(token):
        owner=_access(album,db_provider,token)
        album._verify_post(app,token)
        import fcntl
        folder=_owner_path(album,owner)
        if not folder.is_dir():abort(404)
        with open(folder/'.studio.lock','a+b') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:abort(409)
            db=_db(album,owner)
            if db:
                try:
                    try:row=db.execute('SELECT filename FROM studio_films WHERE athlete_id=?',(owner,)).fetchone()
                    except sqlite3.OperationalError:row=None
                    if row:
                        db.execute('DELETE FROM studio_films WHERE athlete_id=?',(owner,))
                        db.commit()
                        if re.fullmatch(r'studio_[0-9a-f]{28}\.mp4',row['filename']):
                            f=folder/row['filename']
                            if f.is_file() and not f.is_symlink():f.unlink()
                finally:db.close()
        return album._no_cache(redirect(f'/app-tesserato/{token}/studio',code=303))

    # A351 delete/clear must also erase derived A355 video: a family must not
    # accidentally retain pictures in a rendered film after deleting originals.
    import fcntl
    from functools import wraps
    def erase_derived(owner,erase_history=False):
        db=_db(album,owner)
        if db is None:return
        try:
            try: row=db.execute('SELECT filename FROM studio_films WHERE athlete_id=?',(owner,)).fetchone()
            except sqlite3.OperationalError:row=None
            if row:
                db.execute('DELETE FROM studio_films WHERE athlete_id=?',(owner,))
            if erase_history:
                try:db.execute('DELETE FROM studio_events WHERE athlete_id=?',(owner,))
                except sqlite3.OperationalError:pass
            db.commit()
        finally:db.close()
        if row and re.fullmatch(r'studio_[0-9a-f]{28}\.mp4',row['filename']):
            path=_owner_path(album,owner)/row['filename']
            if path.is_file() and not path.is_symlink():path.unlink()

    for endpoint in ('a351_album_clear','a351_album_delete'):
        original=app.view_functions[endpoint]
        def wrapped(token,_original=original,_endpoint=endpoint,**kwargs):
            owner=_access(album,db_provider,token)
            folder=_owner_path(album,owner)
            if not folder.is_dir():
                return _original(token,**kwargs)
            lockfile=folder/'.studio.lock'
            if lockfile.is_symlink():abort(500)
            with open(lockfile,'a+b') as lock:
                os.chmod(lockfile,0o600)
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:abort(409,'Un montaggio è in corso.')
                response=_original(token,**kwargs)
                if response.status_code==303:
                    erase_derived(owner,erase_history=(_endpoint=='a351_album_clear'))
                return response
        app.view_functions[endpoint]=wrapped

    routes=[
      (base,'a355_studio_home',home,['GET']),
      (base+'/render','a355_studio_render',render,['POST']),
      (base+'/film','a355_studio_film',lambda token:media(token,False),['GET']),
      (base+'/download','a355_studio_download',lambda token:media(token,True),['GET']),
      (base+'/delete','a355_studio_delete',erase,['POST']),
    ]
    for path,endpoint,handler,methods in routes:
        app.add_url_rule(path,endpoint,handler,methods=methods)
