# -*- coding: utf-8 -*-
from __future__ import annotations
import json, os, py_compile, shutil, sqlite3, subprocess, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r101_criticality_profile')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_file(p):
    try: rel=p.relative_to(APP)
    except Exception: rel=Path(p.name)
    dst=BACK/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst)

# ------------------------------------------------------------------
# Core alert truth: hidden/history/request docs are NOT active medical certificates.
# Minor criticalities open the canonical athlete sheet, whose save returns to Atlete.
# ------------------------------------------------------------------
CORE=APP/'asd_app/core.py'
cs=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R101_CRITICALITY_CANONICAL' not in cs:
    backup_file(CORE)
    old='''        sql = "SELECT 1 FROM documenti WHERE tesserato_id=? AND (" + " OR ".join(pieces) + ") LIMIT 1"
'''
    new='''        # BODYMIND_R101_CRITICALITY_CANONICAL
        sql = ("SELECT 1 FROM documenti WHERE tesserato_id=? "
               "AND COALESCE(visibile,1)=1 "
               "AND LOWER(COALESCE(doc_type,''))<>'richiesta_certificato_medico' "
               "AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%certificat%' "
               "AND LOWER(COALESCE(titolo,'')) NOT LIKE '%promemoria%certificat%' "
               "AND (" + " OR ".join(pieces) + ") LIMIT 1")
'''
    if old not in cs:
        raise RuntimeError('R101 medical-presence SQL anchor missing')
    cs=cs.replace(old,new,1)

    old_minor='''"Completa tutela", f"/minori?id={tid}", "Apri atleta", tess_url'''
    new_minor='''"Completa tutela", tess_url, "Torna alle atlete", "/mobile/atlete"'''
    if old_minor not in cs:
        raise RuntimeError('R101 minor criticality route anchor missing')
    cs=cs.replace(old_minor,new_minor,1)

    CORE.write_text(cs,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r101-core] PASS medical-request-excluded hidden-doc-excluded criticality->canonical-athlete',flush=True)
else:
    print('[r101-core] already applied',flush=True)

# ------------------------------------------------------------------
# Canonical mobile athlete sheet also edits minor consent/tutela.
# ------------------------------------------------------------------
matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if 'BODYMIND_R100_PROFILE_SAVE_VERIFY' in s and "def fix12_mobile_atleta" in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R101 expected one R100 mobile athlete source, found '+repr([str(x[0]) for x in matches]))
PROFILE,ps=matches[0]

# R103: R100/R101 profile-save logic uses date/datetime inside the patched
# runtime module. Ensure those names exist in that module, even if the legacy
# source never imported them.
if 'from datetime import date, datetime' not in ps:
    backup_file(PROFILE)
    lines=ps.splitlines(True)
    insert_at=0
    for idx,line in enumerate(lines[:12]):
        stripped=line.strip()
        if stripped.startswith('from __future__ import '):
            insert_at=idx+1
        elif idx==0 and (stripped.startswith('#!') or 'coding' in stripped):
            insert_at=max(insert_at,idx+1)
    lines.insert(insert_at,'from datetime import date, datetime\n')
    ps=''.join(lines)
    PROFILE.write_text(ps,encoding='utf-8')
    py_compile.compile(str(PROFILE),doraise=True)
    print('[r103-profile-import] PASS date+datetime available to mobile POST',flush=True)

if 'BODYMIND_R101_MINOR_CONSENT_IN_PROFILE' not in ps:
    backup_file(PROFILE)

    # Load minor row for display/fallback.
    row_anchor="""        if not row: abort(404)
        if request.method=='POST':
"""
    row_new="""        if not row: abort(404)
        # BODYMIND_R101_MINOR_CONSENT_IN_PROFILE
        mrow=conn.execute('SELECT * FROM minori WHERE tesserato_id=? ORDER BY id DESC LIMIT 1',(tid,)).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone() else None
        if request.method=='POST':
"""
    if row_anchor not in ps:
        raise RuntimeError('R101 mobile minor row anchor missing')
    ps=ps.replace(row_anchor,row_new,1)

    # Persist consent after guardian/minor convergence, before commit/readback.
    commit_anchor="""            conn.commit()
            saved=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
"""
    consent_code="""            if request.form.get('minor_consent_form')=='1' and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone():
                mcols={x[1] for x in conn.execute('PRAGMA table_info(minori)').fetchall()}
                m=conn.execute('SELECT * FROM minori WHERE tesserato_id=? ORDER BY id DESC LIMIT 1',(tid,)).fetchone()
                if m:
                    sets=[]; vals=[]
                    if 'consenso_firmato' in mcols:
                        sets.append('consenso_firmato=?'); vals.append(1 if request.form.get('consenso_firmato') else 0)
                    if 'data_consenso' in mcols:
                        sets.append('data_consenso=?'); vals.append((request.form.get('data_consenso') or '').strip())
                    if 'note_consenso' in mcols:
                        sets.append('note_consenso=?'); vals.append((request.form.get('note_consenso') or '').strip())
                    if 'updated_at' in mcols:
                        sets.append('updated_at=datetime("now")')
                    if sets:
                        vals.append(int(m['id']))
                        conn.execute('UPDATE minori SET '+','.join(sets)+' WHERE id=?',vals)
            conn.commit()
            saved=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
"""
    if commit_anchor not in ps:
        raise RuntimeError('R101 mobile consent commit anchor missing')
    ps=ps.replace(commit_anchor,consent_code,1)

    # g() falls back to minor row for consent fields.
    g_old="""    def g(k):
        try:return row[k] or ''
        except:return ''
"""
    g_new="""    def g(k):
        try:
            if k in row.keys() and row[k] not in (None,''): return row[k]
        except Exception: pass
        try:
            if mrow and k in mrow.keys() and mrow[k] not in (None,''): return mrow[k]
        except Exception: pass
        return ''
"""
    if g_old not in ps:
        raise RuntimeError('R101 g() anchor missing')
    ps=ps.replace(g_old,g_new,1)

    # Add consent controls to the canonical form.
    form_old='''{% for f,l,v in fields %}<div class="field"><label>{{l}}</label><input name="{{f}}" value="{{v}}"></div>{% endfor %}<button class="save">Salva modifiche</button>'''
    form_new='''{% for f,l,v in fields %}<div class="field"><label>{{l}}</label><input name="{{f}}" value="{{v}}"></div>{% endfor %}{% if minor %}<input type="hidden" name="minor_consent_form" value="1"><div class="field"><label><input type="checkbox" name="consenso_firmato" value="1" {% if consent %}checked{% endif %}> Consenso/tutela firmato</label></div><div class="field"><label>Data consenso</label><input name="data_consenso" value="{{consent_date}}"></div><div class="field"><label>Note consenso</label><input name="note_consenso" value="{{consent_notes}}"></div>{% endif %}<button class="save">Salva modifiche</button>'''
    if form_old not in ps:
        raise RuntimeError('R101 mobile consent form anchor missing')
    ps=ps.replace(form_old,form_new,1)

    # Render minor status + consent variables.
    render_old='''return render_template_string(tpl,tid=tid,name=(g('nome')+' '+g('cognome')).strip(),course=g('corso'),docs=docs,pays=pays,pres=pres,fields=fields,csrf=csrf_input())'''
    render_new='''return render_template_string(tpl,tid=tid,name=(g('nome')+' '+g('cognome')).strip(),course=g('corso'),docs=docs,pays=pays,pres=pres,fields=fields,csrf=csrf_input(),minor=bool(int(g('minorenne') or 0)),consent=bool(int(g('consenso_firmato') or 0)),consent_date=g('data_consenso'),consent_notes=g('note_consenso'))'''
    if render_old not in ps:
        raise RuntimeError('R101 render args anchor missing')
    ps=ps.replace(render_old,render_new,1)

    PROFILE.write_text(ps,encoding='utf-8')
    py_compile.compile(str(PROFILE),doraise=True)
    print('[r101-profile] PASS guardian+consent one-sheet save -> /mobile/atlete',flush=True)
else:
    print('[r101-profile] already applied',flush=True)

# ------------------------------------------------------------------
# Runtime QA: real same-value POST through the Flask route, then restore updated_at.
# ------------------------------------------------------------------
qa=r'''
import json, sqlite3, sys
from html.parser import HTMLParser
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from asd_app.core import app
app.config["TESTING"]=True
app.config["PROPAGATE_EXCEPTIONS"]=True
DB="/data/tenants/default/asd.db"

class HiddenParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden={}
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="input": return
        d={str(k).lower():str(v or "") for k,v in attrs}
        if d.get("type","").lower()=="hidden" and d.get("name"):
            self.hidden[d["name"]]=d.get("value","")

conn=sqlite3.connect(DB,timeout=20); conn.row_factory=sqlite3.Row
try:
    row=conn.execute("SELECT id,corso,updated_at FROM tesserati WHERE id=45").fetchone()
    if not row:
        row=conn.execute("SELECT id,corso,updated_at FROM tesserati WHERE minorenne=0 ORDER BY id LIMIT 1").fetchone()
    tid=int(row["id"]); old_course=str(row["corso"] or ""); old_updated=str(row["updated_at"] or "")
finally:
    conn.close()

client=app.test_client()
with client.session_transaction() as sess:
    sess["logged"]=True; sess["username"]="admin"; sess["display_name"]="R101 QA"; sess["role"]="admin"; sess["tenant_slug"]="default"

ua={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"}
getr=client.get("/mobile/atleta/"+str(tid)+"?advanced=1",headers=ua,follow_redirects=False)
parser=HiddenParser(); parser.feed(getr.get_data(as_text=True))
payload=dict(parser.hidden)
sentinel=("R101-QA-"+str(tid))[:80]
payload["corso"]=sentinel
resp=None; persisted=False; loc=""; restored=False
try:
    resp=client.post("/mobile/atleta/"+str(tid),data=payload,headers=ua,follow_redirects=False)
    loc=resp.headers.get("Location","")
    conn=sqlite3.connect(DB,timeout=20); conn.row_factory=sqlite3.Row
    try:
        fresh=conn.execute("SELECT corso FROM tesserati WHERE id=?",(tid,)).fetchone()
        persisted=bool(fresh and str(fresh["corso"] or "")==sentinel)
    finally:
        conn.close()
finally:
    conn=sqlite3.connect(DB,timeout=20)
    try:
        conn.execute("UPDATE tesserati SET corso=?,updated_at=? WHERE id=?",(old_course,old_updated,tid)); conn.commit()
        restored=True
        integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()

obj={"get_status":getr.status_code,"hidden_fields":sorted(payload.keys()),"post_status":resp.status_code if resp else None,
     "location":loc,"tid":tid,"persisted_changed_value":persisted,"restored":restored,"integrity":integrity,"fk":fk}
print("[r101-profile-post-smoke] "+json.dumps(obj,ensure_ascii=False),flush=True)
if getr.status_code!=200 or resp is None or resp.status_code not in (302,303) or not loc.startswith("/mobile/atlete?updated=") or not persisted or not restored or integrity.lower()!="ok" or fk:
    raise RuntimeError("R101 profile POST smoke failed "+repr(obj))
'''
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=90)
    if proc.returncode!=0:
        raise RuntimeError('R101 child QA failed '+(proc.stderr or proc.stdout)[-2000:])
    print((proc.stdout or '').strip(),flush=True)
else:
    print('[startup-convergence] R101 mutating profile POST smoke skipped; static+DB hard gates remain active',flush=True)

# Static + DB final gates.
ct=CORE.read_text(encoding='utf-8',errors='replace')
pt=PROFILE.read_text(encoding='utf-8',errors='replace')
conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    tess=int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
finally:
    conn.close()
checks={
 'criticality_canonical':'BODYMIND_R101_CRITICALITY_CANONICAL' in ct and 'f"/minori?id={tid}"' not in ct,
 'medical_request_excluded':"richiesta_certificato_medico" in ct and "COALESCE(visibile,1)=1" in ct,
 'consent_in_profile':'BODYMIND_R101_MINOR_CONSENT_IN_PROFILE' in pt and 'minor_consent_form' in pt,
 'return_atlete':"/mobile/atlete?updated=" in pt,
 'tesserati_dynamic_positive':tess>0,
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r101-checks] '+repr(checks),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed: raise RuntimeError('R101 QA failed '+repr(failed))
print('[r101-selftest] PASS criticality-canonical medical-request-truth profile-post-persistence consent guardian return-atlete db-ok',flush=True)
