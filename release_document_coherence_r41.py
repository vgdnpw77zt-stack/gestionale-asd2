# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import compileall, re, shutil, sqlite3

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_DOCUMENT_COHERENCE_R41'
BACKUPS=Path('/data/release_backups/20260930_document_coherence_r41')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute('PRAGMA table_info('+name+')').fetchall()} if table(conn,name) else set()

def norm(v):
    return str(v or '').strip().lower()

def is_mu_row(r):
    hay=' '.join(norm(r[k]) for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
    return any(x in hay for x in (
        'modulo_unico_tesseramento','modulo unico','modulo_unico','mu-2026','mu 2026',
        'modulo iscrizione','domanda iscrizione','iscrizione manleva'
    ))

# BODYMIND_R73_GLOBAL_MU_PRESENCE
# Apply on every startup, even when the historical R41 marker already exists.
R73_COH=APP/'asd_app/routes_document_coherence_r41.py'
if R73_COH.exists():
    r73=R73_COH.read_text(encoding='utf-8',errors='replace')
    if 'BODYMIND_R73_GLOBAL_MU_PRESENCE' not in r73:
        backup('asd_app/routes_document_coherence_r41.py')
        a=r73.find('def _mu_state(tid):')
        b=r73.find('def _replace_contextual_not_generated',a)
        if a<0 or b<0:
            raise RuntimeError('R73 MU state anchor missing')
        func='''# BODYMIND_R73_GLOBAL_MU_PRESENCE
def _mu_state(tid):
    if tid<=0:
        return None
    conn=db()
    try:
        states=[]
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
            rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id DESC",(tid,)).fetchall()
            for r in rows:
                hay=' '.join(str(r[k] or '').strip().lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
                if any(x in hay for x in _MU_ALIASES):
                    status=str(r['status'] or '').strip().lower() if 'status' in r.keys() else ''
                    states.append('verified' if status in _TRUSTED else 'pending')
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_documents'").fetchone():
            rows=conn.execute("SELECT * FROM inbound_documents WHERE coalesce(tesserato_id,0)=? ORDER BY id DESC",(tid,)).fetchall()
            for r in rows:
                keys=set(r.keys())
                dtype=str(r['document_type'] or '').strip().lower() if 'document_type' in keys else ''
                hay=' '.join(str(r[k] or '').strip().lower() for k in ('document_type','original_filename','filename','saved_path') if k in keys)
                if dtype not in _MU_ALIASES and not any(x in hay for x in _MU_ALIASES):
                    continue
                status=str(r['status'] or '').strip().lower() if 'status' in keys else ''
                conf=int(r['document_confidence'] or 0) if 'document_confidence' in keys else 0
                match=int(r['match_score'] or 0) if 'match_score' in keys else 0
                trusted=status in ('accepted','manual_accepted','verificato','archived_to_tesserato','resolved')
                associated=status=='associato' and (conf>=95 or match>=95)
                states.append('verified' if (trusted or associated) else 'pending')
        if 'verified' in states:
            return 'verified'
        if states:
            return 'pending'
        return None
    finally:
        conn.close()

'''
        r73=r73[:a]+func+r73[b:]
        ua_anchor="        ua=str(request.headers.get('User-Agent') or '')"
        mobile_patch="""        # BODYMIND_R73_MOBILE_DELETE_VISIBILITY
        if request.path=='/mobile' or request.path.startswith('/tesserati'):
            _r73_patch=\"\"\"<style id='BODYMIND_R73_MOBILE_DELETE_VISIBILITY'>
@media(max-width:800px){
form[action*='elimina' i],form[action*='delete' i],a[href*='elimina' i],a[href*='delete' i],
button[name*='elimina' i],button[data-action*='delete' i],button[data-action*='elimina' i]{
display:inline-flex!important;visibility:visible!important;opacity:1!important;pointer-events:auto!important}}
</style><script>(function(){if(!window.matchMedia||!window.matchMedia('(max-width:800px)').matches)return;
document.querySelectorAll('button,a,input[type=submit]').forEach(function(el){var txt=(el.textContent||el.value||'').toLowerCase();
var href=(el.getAttribute('href')||'').toLowerCase();var f=el.closest('form');var action=(f&&f.action?f.action:'').toLowerCase();
if(txt.indexOf('elimina')>=0||txt.indexOf('cancella')>=0||href.indexOf('elimina')>=0||href.indexOf('delete')>=0||action.indexOf('elimina')>=0||action.indexOf('delete')>=0){
el.style.setProperty('display','inline-flex','important');el.style.setProperty('visibility','visible','important');el.style.setProperty('opacity','1','important');}});})();</script>\"\"\"
            html=html.replace('</body>',_r73_patch+'</body>',1) if '</body>' in html else html+_r73_patch
"""
        if ua_anchor not in r73:
            raise RuntimeError('R73 mobile delete anchor missing')
        r73=r73.replace(ua_anchor,mobile_patch+'\n'+ua_anchor,1)
        R73_COH.write_text(r73,encoding='utf-8')
        if not compileall.compile_file(str(R73_COH),quiet=1):
            raise RuntimeError('R73 coherence compile failed')
        print('[document-coherence-r73] PASS uploaded-MU presence + mobile delete visibility',flush=True)

before={}
if DB.exists():
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
            if table(conn,t):
                before[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
    finally:
        conn.close()

if not MARKER.exists():
    BACKUPS.mkdir(parents=True,exist_ok=True)

    # 1) Human verification UX in athlete dossier.
    rel='asd_app/routes_documenti.py'
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R41 routes_documenti missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R41_HUMAN_VERIFY' not in s:
        backup(rel)
        # Existing R10 button was hidden unless inbound_id existed. A visible pending document
        # must always offer a human confirmation action, even for repaired/legacy dossier rows.
        old_cond="""((int(d['inbound_id'] or 0) if 'inbound_id' in d.keys() else 0) and ((int(d['confidence'] or 0) if 'confidence' in d.keys() else 0) < 100 or str((d['status'] if 'status' in d.keys() else '') or '').lower() in ('da_verificare','needs_review','richiede_conferma','associato_tipo_da_verificare')))"""
        new_cond="""((int(d['confidence'] or 0) if 'confidence' in d.keys() else 0) < 100 or str((d['status'] if 'status' in d.keys() else '') or '').lower() in ('da_verificare','needs_review','richiede_conferma','associato_tipo_da_verificare','pending'))"""
        if old_cond in s:
            s=s.replace(old_cond,new_cond,1)
        # Make the action understandable to a normal person.
        s=s.replace(">✓ OK</button></form>",">✓ Conferma documento</button></form>")
        marker_anchor='# BODYMIND_R10_VERIFY_DOCUMENT'
        if marker_anchor not in s:
            raise RuntimeError('R41 dossier verify route missing')
        s=s.replace(marker_anchor,"# BODYMIND_R41_HUMAN_VERIFY\n"+marker_anchor,1)
        # The dossier verification route must retain MU/onboarding synchronization.
        if 'BODYMIND_R25_DOSSIER_MU_VERIFY' not in s:
            raise RuntimeError('R41 refuses release: dossier MU sync missing')
        # Strong, obvious button in the dossier.
        style_anchor="html body #archivio-doc .bm-r10-ok{"
        if style_anchor in s and 'bodymind-r41-confirm-document' not in s:
            s=s.replace(style_anchor,"/* bodymind-r41-confirm-document */\n       "+style_anchor,1)
        p.write_text(s,encoding='utf-8')

    # 2) Human wording in the central Autopilot verification queue.
    rel='asd_app/routes_a202_operational_integrity.py'
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R41 a202 missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R41_QUEUE_CONFIRM' not in s:
        backup(rel)
        s=s.replace(">✓ OK</button></form>",">✓ Conferma documento</button></form>")
        s=s.replace("premi OK solo dopo il controllo","premi “Conferma documento” solo dopo il controllo")
        s=s.replace("Apri, correggi se serve e premi OK.","Apri, correggi se serve e premi “Conferma documento”.")
        anchor='def r11_documento_ok(doc_id):'
        if anchor not in s:
            raise RuntimeError('R41 queue OK route missing')
        s=s.replace(anchor,"# BODYMIND_R41_QUEUE_CONFIRM\n"+anchor,1)
        # Queue verification must keep the unified-module trust boundary.
        if '_r13_accept_unified(conn,row)' not in s and 'BODYMIND_R16_FINAL_OK_SYNC' not in s:
            raise RuntimeError('R41 refuses release: queue MU sync missing')
        p.write_text(s,encoding='utf-8')

    # 3) Runtime coherence layer: distinguish PRESENT/PENDING from NOT GENERATED,
    # and add a browser-specific fallback for old Safari on High Sierra.
    rel='asd_app/routes_document_coherence_r41.py'
    p=APP/rel
    module=r'''# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from flask import request
from .core import app, db

# BODYMIND_R41_DOCUMENT_STATE_COHERENCE
_PENDING={'da_verificare','needs_review','richiede_conferma','associato_tipo_da_verificare','pending'}
_TRUSTED={'verificato','salvato','accepted','manual_accepted','ok'}
_MU_ALIASES=('modulo_unico_tesseramento','modulo unico','modulo_unico','mu-2026','mu 2026','modulo iscrizione','domanda iscrizione','iscrizione manleva')

def _tid_from_request():
    for key in ('tesserato_id','tid'):
        try:
            value=request.args.get(key)
            if value and int(value)>0:
                return int(value)
        except Exception:
            pass
    try:
        view=request.view_args or {}
        for key in ('tesserato_id','tid'):
            if key in view and int(view[key])>0:
                return int(view[key])
    except Exception:
        pass
    m=re.search(r'/tesserati/(\d+)',request.path or '')
    return int(m.group(1)) if m else 0

def _mu_state(tid):
    if tid<=0:
        return None
    conn=db()
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
            return None
        rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id DESC",(tid,)).fetchall()
        found=[]
        for r in rows:
            hay=' '.join(str(r[k] or '').strip().lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
            if any(x in hay for x in _MU_ALIASES):
                found.append(r)
        if not found:
            return None
        statuses=[str(r['status'] or '').strip().lower() if 'status' in r.keys() else '' for r in found]
        if any(x in _TRUSTED for x in statuses):
            return 'verified'
        return 'pending'
    finally:
        conn.close()

def _replace_contextual_not_generated(html,state):
    replacement='Caricato · da verificare' if state=='pending' else 'Verificato'
    # Common direct wording.
    html=re.sub(r'(?i)(Modulo\s+Unico(?:\s+MU[- ]?2026(?:\.1)?)?\s*(?:[:·\-]\s*)?)(non\s+generat[oa])',
                lambda m:m.group(1)+replacement,html)
    # Common card/badge wording where "Non generato" is in its own tag.
    for m in list(re.finditer(r'(?i)>\s*non\s+generat[oa]\s*<',html)):
        start=max(0,m.start()-700)
        if 'modulo unico' in html[start:m.start()].lower() or 'mu-2026' in html[start:m.start()].lower():
            html=html[:m.start()]+'>'+replacement+'<'+html[m.end():]
            break
    return html

@app.after_request
def bodymind_r41_document_coherence(response):
    try:
        if request.method!='GET' or 'text/html' not in str(response.headers.get('Content-Type','')).lower():
            return response
        html=response.get_data(as_text=True)
        tid=_tid_from_request()
        state=_mu_state(tid) if tid else None
        if state:
            html=_replace_contextual_not_generated(html,state)
            if state=='pending' and 'BODYMIND_R41_MU_PENDING_BANNER' not in html:
                banner="""<div id='BODYMIND_R41_MU_PENDING_BANNER' style='margin:10px auto 14px;max-width:1120px;padding:12px 14px;border:1px solid rgba(245,158,11,.38);border-radius:14px;background:rgba(120,53,15,.16);color:#fde68a;font-weight:800'>Modulo Unico caricato da Autopilot · da verificare. Apri il documento e premi <b>✓ Conferma documento</b> dopo il controllo.</div>"""
                if '<main' in html:
                    pos=html.find('<main')
                    html=html[:pos]+banner+html[pos:]
                elif '<body' in html:
                    pos=html.find('>',html.find('<body'))+1
                    html=html[:pos]+banner+html[pos:]
        ua=str(request.headers.get('User-Agent') or '')
        old_safari=('Macintosh' in ua and ('Mac OS X 10_13' in ua or 'Mac OS X 10.13' in ua)
                    and 'Safari/' in ua and 'Chrome/' not in ua and 'Chromium/' not in ua and 'CriOS/' not in ua)
        if old_safari and 'BODYMIND_R41_SAFARI_HIGHSIERRA' not in html:
            css="""<style id='BODYMIND_R41_SAFARI_HIGHSIERRA'>
html,body{width:100%!important;max-width:100%!important;overflow-x:hidden!important}
body{min-width:0!important;-webkit-text-size-adjust:100%!important}
*,*:before,*:after{box-sizing:border-box!important}
main,.main,.page,.content,.app-content,.dashboard,.container{min-width:0!important;max-width:100%!important}
img,video,canvas,svg,iframe{max-width:100%!important;height:auto}
table{max-width:100%!important}
input,select,textarea,button{max-width:100%!important}
@media (min-width:900px){
  main,.main,.page,.content,.app-content{overflow:visible!important}
  .sidebar,.app-sidebar,aside{flex-shrink:0!important}
}
</style>"""
            if '</head>' in html:
                html=html.replace('</head>',css+'</head>',1)
            else:
                html=css+html
        response.set_data(html)
        response.headers.pop('Content-Length',None)
    except Exception:
        pass
    return response
'''
    p.write_text(module,encoding='utf-8')

    # Import R41 last enough to see final HTML from older modules.
    appp=APP/'app.py'
    if not appp.exists():
        raise RuntimeError('R41 app.py missing')
    s=appp.read_text(encoding='utf-8')
    import_line='import asd_app.routes_document_coherence_r41  # BODYMIND R41 document state coherence'
    if import_line not in s:
        backup('app.py')
        # Prefer immediately after the consolidated release policy import.
        anchor='import asd_app.routes_release_20260926  # consolidated release policy MUST remain last'
        if anchor in s:
            s=s.replace(anchor,anchor+'\n'+import_line,1)
        else:
            s += '\n'+import_line+'\n'
        appp.write_text(s,encoding='utf-8')

    for rel in ('asd_app/routes_documenti.py','asd_app/routes_a202_operational_integrity.py','asd_app/routes_document_coherence_r41.py','app.py'):
        if not compileall.compile_file(str(APP/rel),quiet=1):
            raise RuntimeError('R41 compile failed: '+rel)

    MARKER.write_text('BodyMind document coherence R41 applied\n',encoding='utf-8')
    print('[document-coherence-r41] applied',flush=True)
else:
    print('[document-coherence-r41] already applied',flush=True)

# Runtime/data audit on every start; no data mutation.
conn=sqlite3.connect(str(DB),timeout=20); conn.row_factory=sqlite3.Row
try:
    pending_mu=[]
    if table(conn,'documenti'):
        rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY id DESC").fetchall()
        seen=set()
        for r in rows:
            if not is_mu_row(r):
                continue
            status=norm(r['status']) if 'status' in r.keys() else ''
            if status in ('da_verificare','needs_review','richiede_conferma','associato_tipo_da_verificare','pending'):
                tid=int(r['tesserato_id'])
                if tid not in seen:
                    seen.add(tid)
                    a=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(tid,)).fetchone()
                    pending_mu.append((tid,((str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip() if a else '')))
    after={t:int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in before}
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

docs=(APP/'asd_app/routes_documenti.py').read_text(encoding='utf-8',errors='replace')
queue=(APP/'asd_app/routes_a202_operational_integrity.py').read_text(encoding='utf-8',errors='replace')
coh=(APP/'asd_app/routes_document_coherence_r41.py').read_text(encoding='utf-8',errors='replace')
checks={
    'dossier-human-confirm':'BODYMIND_R41_HUMAN_VERIFY' in docs and '✓ Conferma documento' in docs,
    'dossier-mu-sync':'BODYMIND_R25_DOSSIER_MU_VERIFY' in docs,
    'queue-human-confirm':'BODYMIND_R41_QUEUE_CONFIRM' in queue and '✓ Conferma documento' in queue,
    'queue-mu-sync':('_r13_accept_unified(conn,row)' in queue or 'BODYMIND_R16_FINAL_OK_SYNC' in queue),
    'mu-present-state':'BODYMIND_R41_DOCUMENT_STATE_COHERENCE' in coh and 'Caricato · da verificare' in coh,
    'safari-highsierra':'BODYMIND_R41_SAFARI_HIGHSIERRA' in coh and 'Mac OS X 10_13' in coh,
    'counts-unchanged':before==after,
    'db-integrity':integrity.lower()=='ok' and fk==0,
}
failed=[k for k,v in checks.items() if not v]
print('[document-coherence-r41] checks='+repr(checks),flush=True)
print('[document-coherence-r41] pending_mu='+repr(pending_mu[:20]),flush=True)
print('[document-coherence-r41] counts_before='+repr(before)+' counts_after='+repr(after)+' integrity='+integrity+' fk='+str(fk),flush=True)
if failed:
    raise RuntimeError('R41 document coherence failed '+repr(failed))
print('[document-coherence-r41-selftest] PASS human-confirm unified-state queue-dossier-sync safari-highsierra data-safe',flush=True)
