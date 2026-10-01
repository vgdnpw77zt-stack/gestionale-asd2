from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
MARK=APP/'.BODYMIND_OPERATOR_BATCH_R52'
BACK=Path('/data/release_backups/20261001_operator_r52_batch/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not P.exists():
    raise RuntimeError('operator runtime missing')

s=P.read_text(encoding='utf-8',errors='replace')
old='''    production_mode=str(request.form.get("production_mode") or "1").strip().lower() not in ("0","false","no","off")
    type_hint=str(request.form.get("document_type_hint") or "").strip()
    allowed_hints={'''
new='''    production_mode=str(request.form.get("production_mode") or "1").strip().lower() not in ("0","false","no","off")
    type_hint=str(request.form.get("document_type_hint") or "").strip()
    batch_intent=session.get("bodymind_operator_upload_intent")
    if isinstance(batch_intent,dict) and not type_hint:
        type_hint=str(batch_intent.get("document_type") or "").strip()
        production_mode=bool(batch_intent.get("production"))
    allowed_hints={'''
if old in s:
    if not BACK.exists():
        BACK.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(P,BACK)
    s=s.replace(old,new,1)
elif 'batch_intent=session.get("bodymind_operator_upload_intent")' not in s:
    raise RuntimeError('R52 batch anchor missing')

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
MARK.write_text('R52 conversation batch intent active\n',encoding='utf-8')
print('[operator-r52-batch] PASS conversational-upload-intent',flush=True)
