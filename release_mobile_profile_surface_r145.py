# -*- coding: utf-8 -*-
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r145_mobile_profile_surface')
BACK.mkdir(parents=True,exist_ok=True)

s=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R145_CANONICAL_MOBILE_PROFILE' not in s:
    shutil.copy2(CORE,BACK/'core.py')
    s += r'''

# BODYMIND_R145_CANONICAL_MOBILE_PROFILE
@app.after_request
def _bodymind_r145_canonical_mobile_profile(resp):
    try:
        import re as _re
        m=_re.fullmatch(r'/mobile/atleta/(\d+)/?',request.path or '')
        if request.method!='GET' or not m or request.args.get('advanced')=='1':
            return resp
        if not bool(session.get('logged')):
            return resp
        status=int(getattr(resp,'status_code',200) or 200)
        if status not in (200,301,302,303,307,308):
            return resp
        tid=int(m.group(1))
        from .document_sync_core_r143 import truth as _truth
        conn=db(); conn.row_factory=sqlite3.Row
        try:
            row=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
            if not row:return resp
            tr=_truth(conn,row)
        finally:
            conn.close()

        checks=[
            ('Modulo Unico',tr['mu'],'Presente e apribile' if tr['mu'] else 'Modulo Unico mancante','OK' if tr['mu'] else 'Manca'),
            ('Certificato',tr['med_ok'],tr['med_detail'],tr['med_state']),
            ('Mensile',tr['monthly'],'Pagamento mese corrente registrato' if tr['monthly'] else 'Pagamento mese corrente mancante/incongruente','OK' if tr['monthly'] else 'Manca'),
            ('Tesseramento',tr['enroll'],'Quota stagione corrente registrata' if tr['enroll'] else 'Quota stagione corrente mancante/incongruente','OK' if tr['enroll'] else 'Manca'),
        ]
        if tr['minor']:
            checks.append(('Tutela',tr['tutela'],'Completa' if tr['tutela'] else ('Non valida senza MU' if not tr['mu'] else 'Genitore/contatto/consenso incompleto'),'OK' if tr['tutela'] else 'Manca'))

        name=(str(row['cognome'] or '')+' '+str(row['nome'] or '')).strip()
        cards=[]
        for label,ok,detail,state in checks:
            color='#16a34a' if ok else ('#f59e0b' if state=='Da verificare' else '#dc2626')
            cards.append("<div class='state'><span class='dot' style='background:"+color+"'></span><div><b>"+e(label)+"</b><small>"+e(detail)+"</small></div><strong class='"+('ok' if ok else 'bad')+"'>"+e(state)+"</strong></div>")
        html="""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>BodyMind · """+e(name)+"""</title>
<style>body{margin:0;background:#071426;color:#eaf2ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.page{max-width:700px;margin:auto;padding:16px 14px 100px}.head{padding:18px;border-radius:20px;background:#0d2036;border:1px solid #203b57}.head h1{margin:4px 0}.head p{margin:0;color:#9fb3ca}.overall{display:inline-block;margin-top:10px;padding:8px 11px;border-radius:999px;background:"""+('#14532d' if tr['overall'] else '#7f1d1d')+""";font-weight:950}.state{display:grid;grid-template-columns:16px 1fr auto;gap:9px;align-items:center;padding:14px;margin-top:9px;border-radius:15px;background:#0b1b2e;border:1px solid #1d3651}.dot{width:12px;height:12px;border-radius:50%}.state small{display:block;color:#91a6bd;margin-top:3px}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.actions a{padding:12px;border-radius:13px;background:#163b5f;color:white;text-decoration:none;text-align:center;font-weight:900}.actions a.upload{background:#166534}.ok{color:#86efac}.bad{color:#fca5a5}</style></head><body><main class='page'><section class='head'><small>ATLETA</small><h1>"""+e(name)+"""</h1><p>"""+e(str(row['corso'] or 'Corso non indicato'))+"""</p><span class='overall'>"""+('REGOLARE' if tr['overall'] else 'DA COMPLETARE')+"""</span></section>"""+''.join(cards)+"""<div class='actions'><a href='/mobile/atleta/"""+str(tid)+"""?advanced=1'>Modifica dati</a><a href='/mobile/atleta/"""+str(tid)+"""/documenti'>Documenti</a><a class='upload' href='/mobile/atleta/"""+str(tid)+"""/documenti/carica'>＋ Carica documento</a><a href='/pagamenti?tesserato_id="""+str(tid)+"""'>Pagamenti</a><a href='/mobile/atlete'>Atlete</a><a href='/mobile'>Home</a></div></main></body></html>"""
        resp.set_data(html)
        resp.status_code=200
        resp.headers.pop('Location',None)
        resp.headers['Content-Type']='text/html; charset=utf-8'
    except Exception as exc:
        print('[r145-profile-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r145-profile] installed canonical mobile profile response',flush=True)
else:
    print('[r145-profile] already installed',flush=True)


# BODYMIND_R145_ADVANCED_FORM_READABILITY_V2
# Fix labels in the canonical advanced athlete form source (not post-render).
_profile_hits=[]
for _p in (APP/'asd_app').rglob('*.py'):
    try:_ps=_p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    if 'BODYMIND_R100_PROFILE_SAVE_VERIFY' in _ps and 'def fix12_mobile_atleta' in _ps:
        _profile_hits.append((_p,_ps))
if len(_profile_hits)!=1:
    raise RuntimeError('R145 readability expected one canonical athlete source')
_PROFILE,_ps=_profile_hits[0]
_fs=_ps.find('def fix12_mobile_atleta')
_fe=_ps.find('\n@app.',_fs)
if _fe<0:_fe=len(_ps)
_fb=_ps[_fs:_fe]
if 'data-bm-readable-label="1"' not in _fb:
    _old='<div class="field"><label>'
    if _old not in _fb:
        raise RuntimeError('R145 readability field-label anchor missing')
    _new='<div class="field"><label data-bm-readable-label="1" style="color:#10243a!important;-webkit-text-fill-color:#10243a!important;opacity:1!important;font-weight:800!important">'
    _fb=_fb.replace(_old,_new)
    _ps=_ps[:_fs]+_fb+_ps[_fe:]
    _PROFILE.write_text(_ps,encoding='utf-8')
    py_compile.compile(str(_PROFILE),doraise=True)
    print('[r145-advanced-labels] PASS canonical source labels dark/readable',flush=True)
else:
    print('[r145-advanced-labels] already canonical',flush=True)
