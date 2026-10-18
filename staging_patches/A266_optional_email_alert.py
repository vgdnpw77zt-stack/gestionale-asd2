"""A266 STAGING ONLY: no generic athlete warning for optional email.
Do not remove missing phone, medical certificate, consent or payment notices.
Do not modify production database or install on Railway.
"""
from pathlib import Path
import hashlib
import argparse
import ast

OLD='for col, label in [("telefono","telefono"),("email","email"),("corso","corso"),("data_nascita","data nascita")]:'
NEW='for col, label in [("telefono","telefono"),("corso","corso"),("data_nascita","data nascita")]:  # A266: email opzionale; nessun avviso generico'

def patch(root):
    p=Path(root)/'core.py'
    text=p.read_text(encoding='utf-8')
    if NEW in text:
        return {'changed':False,'sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()}
    if text.count(OLD)!=1:
        raise RuntimeError(f'STOP A266: unexpected email warning anchor (found {text.count(OLD)})')
    modified=text.replace(OLD,NEW,1)
    assert modified.count('"telefono","telefono"')==text.count('"telefono","telefono"')
    assert 'get_operational_alerts' in modified
    ast.parse(modified,filename=str(p))
    p.write_text(modified,encoding='utf-8')
    return {'changed':True,'sha256':hashlib.sha256(modified.encode('utf-8')).hexdigest()}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    args=parser.parse_args();print(patch(args.root))
