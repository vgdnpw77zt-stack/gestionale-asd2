from __future__ import annotations
from pathlib import Path
import compileall, re, shutil, sqlite3

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_OPERATOR_HARDEN_R30'
BACKUPS=Path('/data/release_backups/20260929_operator_r30')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup(p: Path):
    rel=p.relative_to(APP)
    dst=BACKUPS/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dst)

if not MARKER.exists():
    BACKUPS.mkdir(parents=True,exist_ok=True)

    # Remove the only exact route collision found by R27: historical health_a61.
    health_changes=[]
    for p in (APP/'asd_app').rglob('*.py'):
        text=p.read_text(encoding='utf-8',errors='replace')
        idx=text.find('def health_a61')
        if idx<0:
            continue
        start=max(0,idx-8000)
        prefix=text[start:idx]
        matches=list(re.finditer(r'@app\.(?:route|get)\(\s*([\'"])/health\1',prefix))
        if matches:
            m=matches[-1]
            absolute=start+m.start()
            segment=text[absolute:idx]
            changed=segment.replace('/health','/_legacy-health-a61',1)
            backup(p)
            text=text[:absolute]+changed+text[idx:]
            p.write_text(text,encoding='utf-8')
            health_changes.append(str(p.relative_to(APP)))
            break

    # Ensure the old dead demo script cannot reappear from a legacy source fragment.
    core=APP/'asd_app/core.py'
    if core.exists():
        text=core.read_text(encoding='utf-8',errors='replace')
        old=text
        text=text.replace("<script src=\\'/static/demo/demo_wow.js?v=a82-hardening-build\\'></script>","")
        text=text.replace("<script src='/static/demo/demo_wow.js?v=a82-hardening-build'></script>","")
        text=text.replace('<script src="/static/demo/demo_wow.js?v=a82-hardening-build"></script>',"")
        if text!=old:
            backup(core); core.write_text(text,encoding='utf-8')

    op=APP/'asd_app/routes_operator_bodymind.py'
    if not op.exists():
        raise RuntimeError('R30 operator module missing')
    if not compileall.compile_file(str(op),quiet=1):
        raise RuntimeError('R30 operator compile failed')
    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R30 package compile failed')

    op_text=op.read_text(encoding='utf-8',errors='replace')
    required=[
        '/operatore-bodymind','SpeechRecognition','speechSynthesis',
        'process_inbound_attachment','archiviato_asd','register_payment',
        '_mu_review_items','bodymind_operator_mobile_entry','_cloud_ai',
    ]
    missing=[x for x in required if x not in op_text]
    if missing:
        raise RuntimeError('R30 operator selftest missing '+repr(missing))

    # Read-only data safety snapshot.
    dbp=Path('/data/tenants/default/asd.db')
    if dbp.exists():
        conn=sqlite3.connect(str(dbp),timeout=20)
        try:
            integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
            fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
            tess=int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
            docs=int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0])
            inbound=int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0])
            if integrity.lower()!='ok' or fk:
                raise RuntimeError(f'R30 DB integrity failed integrity={integrity} fk={fk}')
            print(f'[operator-r30-audit] integrity={integrity} fk={fk} tesserati={tess} documenti={docs} inbound={inbound}',flush=True)
        finally:
            conn.close()

    MARKER.write_text('BodyMind Operator hardening R30 applied\n',encoding='utf-8')
    print('[operator-r30] applied health_legacy='+repr(health_changes),flush=True)
    print('[operator-r30-selftest] PASS voice-context identity asd-filing mu-review payment-confirm receipt mobile-entry optional-cloud dead-static safety-audit',flush=True)
else:
    print('[operator-r30] already applied',flush=True)
