from pathlib import Path
import tempfile,shutil,hashlib,importlib.util,ast
root=Path(__file__).resolve().parent
# Run against an isolated A265 clone. Pass path as CLI arg for portability.
import sys
source=Path(sys.argv[1])/'core.py'
spec=importlib.util.spec_from_file_location('a266',root/'../staging_patches/A266_optional_email_alert.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as td:
    r=Path(td); shutil.copy2(source,r/'core.py')
    before=(r/'core.py').read_text()
    result=m.patch(r)
    after=(r/'core.py').read_text()
    assert result['changed']
    assert after==before.replace(m.OLD,m.NEW,1)
    assert m.OLD not in after and m.NEW in after
    assert '"telefono","telefono"' in after
    assert '"data_nascita","data nascita"' in after
    assert m.patch(r)['changed'] is False
    ast.parse(after)
    print('A266 PASS: optional email warning removed; other alert logic unchanged; idempotent; syntax valid')
