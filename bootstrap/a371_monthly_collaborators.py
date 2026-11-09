"""A371 BodyMind — monthly-only collaborator hours, signed statements and real folders.

Legacy day-based entries, receipts, and payments are preserved. Monthly entries use
a dated PERIOD ANCHOR in the existing ledger, but are explicitly identified in a
separate keyed metadata table and never represented as hours worked on that date.
New entries are refused if pre-existing daily hours exist in the same period.
All documents persist under the tenant's existing ASD document volume.
"""
from __future__ import annotations
import hashlib
import io
import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from html import escape as hx
from pathlib import Path
from urllib.parse import urlencode, quote

from flask import abort, make_response, redirect, request, send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

RELEASE = "A371"
DDL_M = """CREATE TABLE IF NOT EXISTS bodymind_collab_monthly (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 collaboratore_id INTEGER NOT NULL,
 anno INTEGER NOT NULL, mese INTEGER NOT NULL,
 ore_id INTEGER NOT NULL UNIQUE, minuti INTEGER NOT NULL,
 tariffa_centesimi INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 creato_il TEXT NOT NULL, aggiornato_il TEXT NOT NULL,
 UNIQUE(collaboratore_id,anno,mese),
 FOREIGN KEY(collaboratore_id) REFERENCES collaboratori(id),
 FOREIGN KEY(ore_id) REFERENCES ore_collaboratori(id)
)"""
DDL_D = """CREATE TABLE IF NOT EXISTS bodymind_collab_monthly_docs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 mensile_id INTEGER NOT NULL,
 revision INTEGER NOT NULL,
 tipo TEXT NOT NULL CHECK(tipo IN ('da_firmare','firmato')),
 percorso TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
 nome_originale TEXT, registrato_il TEXT NOT NULL,
 FOREIGN KEY(mensile_id) REFERENCES bodymind_collab_monthly(id)
)"""
MAX_BYTES = 16 * 1024 * 1024
STATUS_MSG = {
 'salvato':'Ore mensili registrate. Ora puoi generare il foglio per la firma.',
 'generato':'Foglio PDF creato e archiviato nella cartella del collaboratore.',
 'firmato':'Documento firmato archiviato. Il file originale è stato conservato.',
 'liquidato':'Pagamento registrato e ricevuta collaboratore disponibile.'
}

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def valid_period(anno, mese):
    try: y, m = int(anno), int(mese)
    except (TypeError,ValueError): raise ValueError('Anno e mese non validi')
    if not 2020 <= y <= 2100 or not 1 <= m <= 12:
        raise ValueError('Anno o mese fuori intervallo')
    return y,m

def valid_hours(hours, minutes, y, m):
    try: h, n = int(hours), int(minutes)
    except (TypeError,ValueError): raise ValueError('Ore e minuti devono essere numeri interi')
    if h < 0 or n < 0 or n >= 60 or (h == 0 and n == 0):
        raise ValueError('Indica ore maggiori di zero e minuti compresi tra 0 e 59')
    if h*60+n > 31*24*60:
        raise ValueError('Ore del mese oltre il massimo possibile')
    return h*60+n

def valid_rate(value):
    try:
        v=Decimal(str(value or '').replace(',','.')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        cents=int(v*100)
    except (InvalidOperation,ValueError):
        raise ValueError('Tariffa oraria non valida')
    if cents<=0 or cents>100000:
        raise ValueError('Tariffa oraria fuori intervallo')
    return cents

def money(cents):
    return f"{cents/100:,.2f}".replace(',','_').replace('.',',').replace('_','.') + " €"

def gross_cents(minuti,rate):
    return int((Decimal(minuti)*Decimal(rate)/Decimal(60)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def format_hours(minuti):
    return f"{minuti//60} ore e {minuti%60:02d} minuti"

def slug(text):
    x=unicodedata.normalize('NFKD',str(text or '')).encode('ascii','ignore').decode('ascii')
    return re.sub(r'_+','_',re.sub(r'[^A-Za-z0-9]+','_',x)).strip('_')[:52] or 'Collaboratore'

def collaborator_folder(asd_root, collab, create=False):
    base=Path(asd_root).resolve()
    top=base/'Collaboratori'
    prefix=f"C{int(collab['id']):05d}_"
    candidates=([p for p in top.iterdir() if p.is_dir() and not p.is_symlink() and p.name.startswith(prefix)]
                if top.exists() else [])
    if len(candidates)>1: raise ValueError('Più cartelle per collaboratore: richiede verifica')
    target=(candidates[0] if candidates else
            top/(prefix+slug(str(collab['nome'])+'_'+str(collab['cognome']))))
    if base not in target.resolve().parents:raise ValueError('Percorso archivio non consentito')
    if create:target.mkdir(parents=True,exist_ok=True)
    return target

def period_folder(asd_root, collab, y,m,create=False):
    folder=collaborator_folder(asd_root,collab,create=create)/f'{y:04d}-{m:02d}'
    if create:folder.mkdir(parents=True,exist_ok=True)
    return folder

def exists_table(conn,name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def ensure_tables(conn):
    conn.execute(DDL_M)
    conn.execute(DDL_D)

def month_state(conn,cid,y,m):
    row=None;docs=[]
    if exists_table(conn,'bodymind_collab_monthly'):
        row=conn.execute("""SELECT b.*,o.liquidato AS liquidato
           FROM bodymind_collab_monthly b JOIN ore_collaboratori o ON o.id=b.ore_id
           WHERE b.collaboratore_id=? AND b.anno=? AND b.mese=?""",(cid,y,m)).fetchone()
    if row and exists_table(conn,'bodymind_collab_monthly_docs'):
        docs=conn.execute("SELECT * FROM bodymind_collab_monthly_docs WHERE mensile_id=? ORDER BY id DESC",(row['id'],)).fetchall()
    legacy=conn.execute("""SELECT id,ore,liquidato,data FROM ore_collaboratori
       WHERE collaboratore_id=? AND COALESCE(mese,CAST(strftime('%m',data) AS INTEGER))=?
       AND COALESCE(anno,CAST(strftime('%Y',data) AS INTEGER))=? AND id<>?
       ORDER BY data,id""",(cid,m,y,int(row['ore_id']) if row else -1)).fetchall()
    return row,docs,legacy

def persist_month(conn,cid,y,m,minutes,cents):
    """Transaction-safe: exactly one accounting row/month; no conversion of daily history."""
    collab=conn.execute("SELECT * FROM collaboratori WHERE id=?",(cid,)).fetchone()
    if collab is None:raise ValueError('Collaboratore inesistente')
    row,docs,legacy=month_state(conn,cid,y,m)
    if legacy:raise ValueError('Sono già presenti ore giornaliere in questo mese. Non è possibile sommarle automaticamente: verificare lo storico prima di inserire il riepilogo.')
    if row and int(row['liquidato'] or 0):raise ValueError('Mese già liquidato: impossibile modificarlo')
    if row and any(d['tipo']=='firmato' and d['revision']==row['revision'] for d in docs):
        raise ValueError('Il foglio delle ore è già firmato. Conservare la versione originale e predisporre una rettifica separata.')
    stamp=now_iso()
    if row:
        old=row['minuti'],row['tariffa_centesimi']
        if old==(minutes,cents):return row['id']
        conn.execute("UPDATE ore_collaboratori SET ore=? WHERE id=?",(minutes/60,int(row['ore_id'])))
        conn.execute("""UPDATE bodymind_collab_monthly SET minuti=?,tariffa_centesimi=?,
                    revision=revision+1,aggiornato_il=? WHERE id=?""",(minutes,cents,stamp,row['id']))
        return int(row['id'])
    # The 1st is a PERIOD ANCHOR for compatibility with the old
    # monthly accounting engine, NOT an assertion of work on that day.
    anchor=f'{y:04d}-{m:02d}-01'
    conn.execute("""INSERT INTO ore_collaboratori(collaboratore_id,data,ore,mese,anno,liquidato)
                 VALUES (?,?,?,?,?,0)""",(cid,anchor,minutes/60,m,y))
    hours_id=int(conn.execute('SELECT last_insert_rowid()').fetchone()[0])
    conn.execute("""INSERT INTO bodymind_collab_monthly
              (collaboratore_id,anno,mese,ore_id,minuti,tariffa_centesimi,revision,creato_il,aggiornato_il)
              VALUES (?,?,?,?,?,?,1,?,?)""",(cid,y,m,hours_id,minutes,cents,stamp,stamp))
    return int(conn.execute('SELECT last_insert_rowid()').fetchone()[0])

def pdf_font():
    if 'BM371' not in pdfmetrics.getRegisteredFontNames():
        fp=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        if fp.is_file():pdfmetrics.registerFont(TTFont('BM371',str(fp)))
    return 'BM371' if 'BM371' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'

def generate_pdf(collab,y,m,monthly):
    f=pdf_font()
    stream=io.BytesIO()
    pdf=canvas.Canvas(stream,pagesize=A4)
    pdf.setTitle(f"Conferma ore lavorate {m:02d}/{y} - {collab['nome']} {collab['cognome']}")
    W,H=A4
    pdf.setFillColor(colors.HexColor('#10233b'));pdf.rect(0,H-161,W,161,fill=1,stroke=0)
    pdf.setFont(f,11);pdf.setFillColor(colors.HexColor('#aee3ee'));pdf.drawString(40,H-45,"BODYMIND AERIAL STUDIO ASD")
    pdf.setFont(f,17);pdf.setFillColor(colors.white);pdf.drawString(40,H-83,"CONFERMA MENSILE DELLE ORE")
    pdf.setFont(f,10);pdf.drawString(40,H-107,f"Periodo di riferimento: {m:02d}/{y}")
    pdf.setFillColor(colors.HexColor('#152d47'));pdf.roundRect(37,H-365,W-74,174,13,fill=1,stroke=0)
    name=f"{collab['nome']} {collab['cognome']}"
    lines=[("Collaboratrice / collaboratore",name),("Mese",f"{m:02d}/{y}"),
           ("Totale ore svolte",format_hours(monthly['minuti'])),
           ("Tariffa oraria lorda",money(monthly['tariffa_centesimi'])),
           ("Compenso lordo calcolato",money(gross_cents(monthly['minuti'],monthly['tariffa_centesimi'])))]
    yy=H-222
    for title,value in lines:
        pdf.setFillColor(colors.HexColor('#bbd0e1'));pdf.setFont(f,8.6);pdf.drawString(54,yy,title)
        pdf.setFillColor(colors.white);pdf.setFont(f,10);pdf.drawString(270,yy,str(value)[:60])
        yy-=31
    pdf.setFillColor(colors.HexColor('#152d47'));pdf.setFont(f,11);pdf.drawString(42,H-416,"DICHIARAZIONE DELLA COLLABORATRICE / DEL COLLABORATORE")
    pdf.setFont(f,9.2)
    statement=[
       "Io sottoscritta/o, dopo aver verificato il presente riepilogo,",
       f"confermo di avere effettivamente svolto complessivamente {format_hours(monthly['minuti'])}",
       f"di attivita sportiva concordata con BodyMind nel mese {m:02d}/{y}.",
       "Il presente documento attesta le ore dichiarate e non costituisce",
       "quietanza di pagamento, prova di bonifico o rinuncia a compensi dovuti."
    ]
    for i,line in enumerate(statement):pdf.drawString(42,H-447-i*19,line)
    pdf.setStrokeColor(colors.HexColor('#7996a9'));pdf.line(42,178,288,178);pdf.line(325,178,W-42,178)
    pdf.setFillColor(colors.HexColor('#33465f'));pdf.setFont(f,9)
    pdf.drawString(43,163,"Data e luogo");pdf.drawString(327,163,"Firma della collaboratrice / del collaboratore")
    pdf.setFont(f,8);pdf.drawString(42,78,"Documento generato dal registro mensile BodyMind.")
    pdf.drawString(42,63,"Riferimento: mesi, ore e tariffa registrati; conservare la copia firmata negli atti ASD.")
    pdf.save()
    return stream.getvalue()

def _new_file(path,content):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(content);f.flush();os.fsync(f.fileno())

def _date_label(y,m):
    return f'{m:02d}/{y:04d}'

CSS="""<style id="bm371-css">
.bm371{max-width:1100px;margin:20px auto 85px;padding:12px;color:#eef4fc}
.bm371 *{box-sizing:border-box}.bm371 h1{font-size:clamp(25px,4vw,37px);color:#fff}
.bm371 :is(h2,h3){color:#fff}.bm371 p,.bm371 small{color:#b9d3ea;line-height:1.55}
.bm371 a{color:#b2ebff}.bm371 .top{display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;gap:15px}
.bm371 .panel{padding:19px;margin:15px 0;border:1px solid #527b9d;border-radius:18px;background:#122c45}
.bm371 .tile{border:1px solid #466988;background:#132a40;padding:17px;border-radius:16px;margin:13px 0}
.bm371 .kicker{font-size:11px;letter-spacing:.14em;color:#87cbdc}
.bm371 .form{display:flex;align-items:end;flex-wrap:wrap;gap:12px}
.bm371 label{display:flex;flex-direction:column;gap:7px;color:#e1edfb;flex:1;min-width:125px}
.bm371 :is(select,input,textarea){width:100%;min-height:45px;border:1px solid #668ba8;border-radius:10px;background:#fff;color:#15283b;-webkit-text-fill-color:#15283b;font-size:16px;padding:10px}
.bm371 :is(button,.btn){display:inline-block;min-height:44px;border:1px solid #85dfe9;border-radius:11px;padding:11px 14px;font-weight:800;cursor:pointer;background:#145b81;color:#fff;text-decoration:none}
.bm371 button:disabled{opacity:.5;cursor:not-allowed}
.bm371 .secondary{background:#293f54;border-color:#7796b0}
.bm371 .amber{border:1px solid #bca66e;background:#4a4024;color:#ffeabe;padding:12px;border-radius:12px}
.bm371 .ok{color:#b5f3cf}.bm371 .links{display:flex;gap:9px;flex-wrap:wrap;margin-top:13px}
.bm371 .metric{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;font-size:16px}
.bm371 .metric strong{color:#fff}
@media(max-width:600px){.bm371{padding:7px}.bm371 .panel{padding:13px}.bm371 .form>button{width:100%}}
</style>"""

def render_page(conn,y,m,csrf,root,info=''):
    collabs=conn.execute("SELECT id,nome,cognome,paga_oraria,ruolo,attivo FROM collaboratori ORDER BY cognome,nome").fetchall()
    base='/collaboratori/mensile'
    header=f'''{CSS}<main class="bm371"><div class="top"><div><small class="kicker">BODYMIND · GESTIONE COLLABORATORI</small><h1>Ore mensili e documenti firmati</h1></div>
    <div class="links"><a class="btn secondary" href="/collaboratori?new=1">Nuovo collaboratore</a>
    <a class="btn secondary" href="/documenti/asd/cartelle?cartella=Collaboratori">Archivio cartelle</a>
    <a class="btn secondary" href="/collaboratori?vista=giornaliera&mese={m}&anno={y}">Storico giornaliero precedente</a></div></div>
    <p>Una sola registrazione di ore per mese e per collaboratore. Il foglio da firmare conferma le ore svolte e non sostituisce la ricevuta di pagamento.</p>
    <section class="panel"><form class="form" method="get"><label>Mese<input type="month" name="periodo" value="{y:04d}-{m:02d}" required></label>
    <button>Apri mese</button></form></section>'''
    if info in STATUS_MSG:header+=f'<p class="panel ok" role="status">{hx(STATUS_MSG[info])}</p>'
    cards=[]
    for c in collabs:
        cid=c['id']
        row,docs,legacy=month_state(conn,cid,y,m)
        pdfs=[d for d in docs if d['tipo']=='da_firmare' and d['revision']==row['revision']] if row else []
        signed=[d for d in docs if d['tipo']=='firmato' and d['revision']==row['revision']] if row else []
        locked=bool(row and (row['liquidato'] or signed))
        folder=collaborator_folder(root,c,create=False)
        path=folder.relative_to(root).as_posix()
        link='/documenti/asd/cartelle?'+urlencode({'cartella':path}) if folder.exists() else ''
        rate=(row['tariffa_centesimi']/100 if row else round(float(c['paga_oraria'] or 0),2))
        if row:
            minrec=row['minuti']
            value=f'<div class="metric"><span>Ore registrate <strong>{format_hours(minrec)}</strong></span><span>Compenso lordo <strong>{money(gross_cents(minrec,row["tariffa_centesimi"]))}</strong></span></div>'
        else:value='<p>Nessun riepilogo mensile ancora registrato.</p>'
        legacywarn=''
        if legacy:
            total=sum(Decimal(str(x['ore'] or 0)) for x in legacy)
            legacywarn=f'<p class="amber">Attenzione: {len(legacy)} vecchie righe giornaliere, per complessive {str(total).replace(".",",")} ore, sono già presenti in questo mese. Non vengono sommate al riepilogo mensile per evitare duplicati; verifica lo storico prima di convertirle.</p>'
        fields=''
        if not locked and not legacy:
            hour=row['minuti']//60 if row else ''
            minute=row['minuti']%60 if row else '0'
            fields=f'''<form class="form" method="post" action="{base}/salva">
              {csrf}<input type="hidden" name="collaboratore_id" value="{cid}">
              <input type="hidden" name="anno" value="{y}"><input type="hidden" name="mese" value="{m}">
              <label>Ore totali del mese<input type="number" min="0" max="744" name="ore" required value="{hour}"></label>
              <label>Minuti<input type="number" min="0" max="59" name="minuti" required value="{minute}"></label>
              <label>Tariffa lorda oraria (€)<input type="number" step="0.01" min="0.01" name="tariffa" value="{rate:.2f}" required></label>
              <button type="submit">{'Aggiorna ore mensili' if row else 'Salva ore del mese'}</button></form>'''
        docarea=''
        if row:
            downloadlinks=[]
            for d in docs:
                label=('Foglio da firmare' if d['tipo']=='da_firmare' else 'Foglio firmato')+f' (v{d["revision"]})'
                url='/documenti/asd/download/'+quote(d['percorso'],safe='/')
                downloadlinks.append(f'<a class="btn secondary" href="{hx(url,quote=True)}">{hx(label)}</a>')
            docarea=f'<div class="links">{"".join(downloadlinks) if downloadlinks else "<small>Nessun documento generato.</small>"}</div>'
            if not locked:
                docarea+=f'''<form method="post" action="{base}/genera" class="form" style="margin-top:16px">
                    {csrf}<input type="hidden" name="collaboratore_id" value="{cid}"><input type="hidden" name="anno" value="{y}"><input type="hidden" name="mese" value="{m}">
                    <button type="submit" class="secondary">Genera e archivia foglio PDF da firmare</button></form>'''
            if pdfs and not signed and not row['liquidato']:
                docarea+=f'''<form method="post" enctype="multipart/form-data" action="{base}/carica-firmato" class="form" style="margin-top:16px">
                    {csrf}<input type="hidden" name="collaboratore_id" value="{cid}"><input type="hidden" name="anno" value="{y}"><input type="hidden" name="mese" value="{m}">
                    <label>Carica foglio firmato (PDF, JPG o PNG, max 16 MB)<input type="file" name="allegato" accept=".pdf,.jpg,.jpeg,.png" required></label>
                    <button type="submit">Salva firmato nei documenti</button></form>'''
            if row['liquidato']:
                docarea+='<p class="ok">Periodo liquidato nel registro compensi.</p><div class="links"><a class="btn secondary" href="/collaboratori/ricevute">Apri ricevute collaboratori</a></div>'
            else:
                docarea+=f'''<form method="post" class="form" action="{base}/registra-pagamento" style="margin-top:16px"
                    onsubmit="return confirm('Hai verificato che il pagamento a questo collaboratore sia stato effettuato? Questa azione registrerà una uscita e una ricevuta.');">
                    {csrf}<input type="hidden" name="collaboratore_id" value="{cid}"><input type="hidden" name="anno" value="{y}"><input type="hidden" name="mese" value="{m}">
                    <button type="submit" class="secondary">Registra pagamento effettuato e crea ricevuta</button></form>
                    <small>Non premere prima di aver effettuato il pagamento. Il foglio firmato attesta le ore, non il bonifico.</small>'''
        else:
            docarea='<small>Salva prima le ore del mese per generare il foglio da firmare.</small>'
        folderbtn=(f'<a class="btn secondary" href="{hx(link,quote=True)}">Apri cartella documenti</a>' if link else
                   f'<form method="post" action="{base}/crea-cartella" class="form">{csrf}<input type="hidden" name="collaboratore_id" value="{cid}"><input type="hidden" name="anno" value="{y}"><input type="hidden" name="mese" value="{m}"><button class="secondary">Crea cartella documenti</button></form>')
        cards.append(f'''<section class="tile"><h2>{hx(c['nome'])} {hx(c['cognome'])}</h2>
          <small>{hx(c['ruolo'] or 'Collaboratore')} · ID {cid} · {_date_label(y,m)}</small>
          {value}{legacywarn}{fields}<h3 style="margin-top:20px">Foglio ore e documenti</h3>{docarea}
          <div class="links">{folderbtn}</div></section>''')
    return header+('<section class="panel">'+''.join(cards)+'</section>' if cards else '<p class="panel">Nessun collaboratore. Aggiungine uno prima.</p>')+'</main>'

def _period_from_request():
    period=request.args.get('periodo','')
    if period and re.fullmatch(r'\d{4}-\d{2}',period):
        return valid_period(period[:4],period[5:])
    today=date.today()
    return valid_period(request.values.get('anno',today.year),request.values.get('mese',today.month))

def _params(y,m):
    return urlencode({'periodo':f'{y:04d}-{m:02d}'})

def _require_collab(conn,cid):
    c=conn.execute("SELECT * FROM collaboratori WHERE id=?",(cid,)).fetchone()
    if not c:raise ValueError('Collaboratore non trovato')
    return c

def _snapshot(conn,cid,y,m):
    c=_require_collab(conn,cid)
    row,docs,legacy=month_state(conn,cid,y,m)
    if not row:raise ValueError('Prima registra le ore mensili')
    return c,row,docs

def _posted_ids():
    y,m=valid_period(request.form.get('anno'),request.form.get('mese'))
    try:cid=int(request.form.get('collaboratore_id',''))
    except ValueError:raise ValueError('Collaboratore non valido')
    if cid<=0:raise ValueError('Collaboratore non valido')
    return cid,y,m

def install(app):
    from asd_app.core import (admin_required, auth, has_role, db,
                             get_asd_media_dir, csrf_input, layout)
    base='/collaboratori/mensile'
    existing={r.rule for r in app.url_map.iter_rules()}
    if base in existing:raise RuntimeError('A371 monthly route collision')

    @app.get(base,endpoint='bm371_monthly_hours')
    @admin_required
    def monthly_hours():
        try:y,m=_period_from_request()
        except ValueError:abort(400)
        con=db()
        try:html=render_page(con,y,m,csrf_input(),get_asd_media_dir(),request.args.get('esito',''))
        finally:con.close()
        response=make_response(layout(html))
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-BodyMind-Monthly-Collaborators']=RELEASE
        return response

    @app.post(base+'/salva',endpoint='bm371_monthly_save')
    @admin_required
    def save_hours():
        con=db()
        try:
            cid,y,m=_posted_ids()
            minutes=valid_hours(request.form.get('ore'),request.form.get('minuti'),y,m)
            rate=valid_rate(request.form.get('tariffa'))
            with con:
                ensure_tables(con)
                persist_month(con,cid,y,m,minutes,rate)
        except (ValueError,sqlite3.Error) as e:
            con.rollback()
            return layout(CSS+f'<main class="bm371 panel"><h1>Ore non salvate</h1><p>{hx(str(e))}</p><a href="{base}">Torna alle ore mensili</a></main>'),409
        finally:con.close()
        return redirect(base+'?'+_params(y,m)+'&esito=salvato',303)

    @app.post(base+'/crea-cartella',endpoint='bm371_create_collab_folder')
    @admin_required
    def create_collab_folder():
        con=db()
        try:
            cid,y,m=_posted_ids()
            collab=_require_collab(con,cid)
            period_folder(get_asd_media_dir(),collab,y,m,create=True)
        except (ValueError,OSError) as e:
            return layout(CSS+f'<main class="bm371"><h1>Cartella non creata</h1><p>{hx(str(e))}</p></main>'),400
        finally:con.close()
        return redirect(base+'?'+_params(y,m),303)

    @app.post(base+'/genera',endpoint='bm371_generate_statement')
    @admin_required
    def statement():
        con=db()
        try:
            cid,y,m=_posted_ids()
            collab,row,docs=_snapshot(con,cid,y,m)
            if row['liquidato']:raise ValueError('Mese liquidato: foglio non modificabile')
            content=generate_pdf(collab,y,m,row)
            folder=period_folder(get_asd_media_dir(),collab,y,m,create=True)
            name=f"Foglio_Ore_{y}_{m:02d}_v{row['revision']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.pdf"
            path=folder/name
            rel=path.relative_to(get_asd_media_dir()).as_posix()
            with con:
                ensure_tables(con)
                _new_file(path,content)
                con.execute("""INSERT INTO bodymind_collab_monthly_docs
                  (mensile_id,revision,tipo,percorso,sha256,nome_originale,registrato_il)
                  VALUES (?,?,?,?,?,?,?)""",
                  (row['id'],row['revision'],'da_firmare',rel,hashlib.sha256(content).hexdigest(),name,now_iso()))
        except (ValueError,sqlite3.Error,OSError) as e:
            con.rollback()
            return layout(CSS+f'<main class="bm371"><h1>Foglio non generato</h1><p>{hx(str(e))}</p></main>'),409
        finally:con.close()
        return redirect(base+'?'+_params(y,m)+'&esito=generato',303)

    @app.post(base+'/carica-firmato',endpoint='bm371_upload_signed')
    @admin_required
    def signed():
        con=db()
        try:
            cid,y,m=_posted_ids()
            collab,row,docs=_snapshot(con,cid,y,m)
            if row['liquidato']:raise ValueError('Mese già liquidato: caricare una rettifica separata')
            if not any(d['tipo']=='da_firmare' and d['revision']==row['revision'] for d in docs):
                raise ValueError('Genera prima il foglio corretto da far firmare')
            upload=request.files.get('allegato')
            if not upload or not upload.filename:raise ValueError('Seleziona il documento firmato')
            ext=Path(upload.filename).suffix.lower()
            if ext not in {'.pdf','.jpg','.jpeg','.png'}:raise ValueError('Formato non ammesso: usare PDF, JPG o PNG')
            content=upload.stream.read(MAX_BYTES+1)
            if not content or len(content)>MAX_BYTES:raise ValueError('File vuoto o superiore a 16 MB')
            valid=(content.startswith(b'%PDF-') if ext=='.pdf' else
                   content.startswith(b'\x89PNG\r\n\x1a\n') if ext=='.png' else
                   content.startswith(b'\xff\xd8\xff'))
            if not valid:raise ValueError('Contenuto non coerente con il formato indicato')
            folder=period_folder(get_asd_media_dir(),collab,y,m,create=True)
            filename=f"Foglio_Ore_FIRMATO_{y}_{m:02d}_v{row['revision']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}{ext}"
            dest=folder/filename
            rel=dest.relative_to(get_asd_media_dir()).as_posix()
            with con:
                ensure_tables(con)
                # A signed declaration must relate to the current monthly revision.
                current=con.execute('SELECT revision FROM bodymind_collab_monthly WHERE id=?',(row['id'],)).fetchone()
                if not current or current['revision']!=row['revision']:raise ValueError('Riepilogo modificato: aggiorna pagina')
                _new_file(dest,content)
                con.execute("""INSERT INTO bodymind_collab_monthly_docs
                 (mensile_id,revision,tipo,percorso,sha256,nome_originale,registrato_il)
                 VALUES (?,?,?,?,?,?,?)""",
                 (row['id'],row['revision'],'firmato',rel,hashlib.sha256(content).hexdigest(),
                  Path(upload.filename).name[:160],now_iso()))
        except (ValueError,sqlite3.Error,OSError) as e:
            con.rollback()
            return layout(CSS+f'<main class="bm371"><h1>Documento non salvato</h1><p>{hx(str(e))}</p></main>'),409
        finally:con.close()
        return redirect(base+'?'+_params(y,m)+'&esito=firmato',303)

    @app.post(base+'/registra-pagamento',endpoint='bm371_record_payment')
    @admin_required
    def register_payment():
        con=db()
        try:
            cid,y,m=_posted_ids()
            with con:
                collab,row,docs=_snapshot(con,cid,y,m)
                if row['liquidato']:raise ValueError('Mese già liquidato')
                if con.execute("""SELECT 1 FROM collaboratori_ricevute
                    WHERE collaboratore_id=? AND anno=? AND mese=?""",(cid,y,m)).fetchone():
                    raise ValueError('Esiste già una ricevuta per questo mese: verificare prima di duplicare il pagamento')
                # No duplicate days: only this single monthly anchor is eligible.
                _,_,legacy=month_state(con,cid,y,m)
                if legacy:raise ValueError('Righe giornaliere presenti: chiusura bloccata per evitare doppi conteggi')
                cents=gross_cents(row['minuti'],row['tariffa_centesimi'])
                amount=cents/100
                desc=f"Compenso collaboratore {collab['nome']} {collab['cognome']} - {m:02d}/{y:04d}"
                stamp=date.today().isoformat()
                con.execute("INSERT INTO movimenti(tipo,categoria,descrizione,importo,data) VALUES (?,?,?,?,?)",
                            ('uscita','collaboratori',desc,amount,stamp))
                movement_id=int(con.execute('SELECT last_insert_rowid()').fetchone()[0])
                pdfname=f"ricevuta_collaboratore_{cid}_{y}_{m:02d}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.pdf"
                con.execute("""INSERT INTO collaboratori_ricevute
                  (collaboratore_id,mese,anno,totale_ore,paga_oraria,totale_compenso,
                   data_generazione,filename,movimento_id)
                  VALUES (?,?,?,?,?,?,?,?,?)""",
                  (cid,m,y,round(row['minuti']/60,2),row['tariffa_centesimi']/100,amount,stamp,pdfname,movement_id))
                con.execute("UPDATE ore_collaboratori SET liquidato=1 WHERE id=? AND COALESCE(liquidato,0)=0",(row['ore_id'],))
                if con.execute('SELECT changes()').fetchone()[0]!=1:
                    raise ValueError('Registrazione già liquidata da un altro operatore')
        except (ValueError,sqlite3.Error) as e:
            con.rollback()
            return layout(CSS+f'<main class="bm371"><h1>Pagamento non registrato</h1><p>{hx(str(e))}</p></main>'),409
        finally:con.close()
        return redirect(base+'?'+_params(y,m)+'&esito=liquidato',303)

    @app.post('/documenti/asd/cartelle/crea',endpoint='bm371_create_general_folder')
    @admin_required
    def create_folder():
        from a370_asd_folder_browser import safe_folder
        root=get_asd_media_dir()
        parent=request.form.get('cartella','')
        raw=(request.form.get('nome') or '').strip()
        if (not 1 <= len(raw) <= 85 or raw in ('.','..') or raw.startswith('.')
                or '/' in raw or '\\' in raw or any(ord(c)<32 for c in raw)):
            return layout(CSS+'<main class="bm371"><h1>Nome cartella non valido</h1></main>'),400
        try:
            parentdir=safe_folder(root,parent)
            dest=parentdir/raw
            if dest.is_symlink():raise ValueError('Collegamenti simbolici non ammessi')
            if dest.exists() and not dest.is_dir():raise ValueError('Esiste già un file con questo nome')
            dest.mkdir(exist_ok=True)
        except (ValueError,OSError) as e:
            return layout(CSS+f'<main class="bm371"><h1>Cartella non creata</h1><p>{hx(str(e))}</p></main>'),400
        return redirect('/documenti/asd/cartelle?'+urlencode({'cartella':dest.relative_to(root).as_posix()}),303)

    @app.before_request
    def enforce_monthly_default_and_privacy():
        path=request.path or ''
        if request.method=='GET' and path=='/collaboratori':
            if request.args.get('new')=='1' or request.args.get('edit') or request.args.get('vista')=='giornaliera':
                return None
            y,m=_period_from_request()
            return redirect(base+'?'+_params(y,m),302)
        if path.startswith(('/documenti/asd/download/Collaboratori/',
                             '/documenti/asd/preview/Collaboratori/')):
            if not auth() or not has_role('admin'):abort(403)
        if request.method=='POST' and path=='/collaboratori/chiudi_mese':
            # Do not close the same monthly entry twice through the legacy route.
            try:
                cid=int(request.form.get('collaboratore_id') or 0)
                y,m=valid_period(request.form.get('anno'),request.form.get('mese'))
            except (ValueError,TypeError):return None
            con=db()
            try:row,_,_=month_state(con,cid,y,m)
            finally:con.close()
            if row: return layout(CSS+'<main class="bm371"><h1>Chiusura mese gestita dal riepilogo mensile</h1><p>Usa il tasto di registrazione pagamento nella pagina Ore mensili.</p></main>'),409
        if request.method=='POST' and path=='/collaboratori':
            if request.form.get('action') in {'create_ora','update_ora'}:
                return layout(CSS+'<main class="bm371"><h1>Registrazioni giornaliere disattivate</h1><p>Usa il riepilogo mensile. Le vecchie righe restano in archivio.</p></main>'),409

    @app.after_request
    def add_folder_form(response):
        if (request.endpoint!='bm370_asd_folders' or response.status_code!=200
              or response.mimetype!='text/html' or response.direct_passthrough):
            return response
        page=response.get_data(as_text=True)
        if 'id="bm371-folder-create"' in page:return response
        parent=request.args.get('cartella','')
        form=f'''<section id="bm371-folder-create" class="bm371 panel" style="margin:18px auto">
          <h2>Crea una nuova cartella nell’archivio ASD</h2>
          <p>La cartella verrà creata sul volume permanente e resterà consultabile da qui.</p>
          <form method="post" action="/documenti/asd/cartelle/crea" class="form">
          {csrf_input()}<input type="hidden" name="cartella" value="{hx(parent,quote=True)}">
          <label>Nome cartella<input name="nome" required maxlength="85" placeholder="Es. Verbali 2026"></label>
          <button type="submit">Crea cartella</button></form></section>'''
        if '</main>' in page:
            page=page.replace('</main>',form+'</main>',1)
            response.set_data(page);response.headers.pop('ETag',None)
            response.headers['Cache-Control']='private, no-store'
        return response

    print('BODYMIND A371 MONTHLY COLLABORATORS READY — month ledger, signed PDFs, persistent folders',flush=True)
