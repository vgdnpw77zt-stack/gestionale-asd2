"""Synthetic two-family document isolation test; never queries production records."""
from pathlib import Path
import ast
import copy
import sqlite3

def validate_candidate(candidate_source,temp_root):
    tree=ast.parse(candidate_source)
    defs=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='bodymind_doc']
    assert len(defs)==1,'document handler mismatch'
    node=copy.deepcopy(defs[0])
    node.decorator_list=[]
    ns={}
    class HTTPNotFound(Exception):
        pass
    def abort(status):
        assert status==404
        raise HTTPNotFound('404')
    (temp_root/'tesserati'/'1').mkdir(parents=True)
    (temp_root/'tesserati'/'2').mkdir(parents=True)
    (temp_root/'tesserati'/'1'/'alpha.pdf').write_bytes(b'%PDF-SYNTHETIC-ALPHA')
    (temp_root/'tesserati'/'2'/'beta.pdf').write_bytes(b'%PDF-SYNTHETIC-BETA')
    keeper=sqlite3.connect('file:a350_synthetic_family?mode=memory&cache=shared',uri=True)
    keeper.executescript("""
    CREATE TABLE tesserati(id INTEGER PRIMARY KEY,online_token TEXT UNIQUE NOT NULL);
    CREATE TABLE documenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER,
      note TEXT,visibile INTEGER,filename TEXT,original_filename TEXT);
    INSERT INTO tesserati VALUES(1,'A350_SYNTH_ALPHA');
    INSERT INTO tesserati VALUES(2,'A350_SYNTH_BETA');
    INSERT INTO documenti VALUES(101,1,'',1,'tesserati/1/alpha.pdf','alpha.pdf');
    INSERT INTO documenti VALUES(102,1,'',0,'tesserati/1/alpha.pdf','hidden.pdf');
    INSERT INTO documenti VALUES(103,1,'',NULL,'tesserati/1/alpha.pdf','null.pdf');
    INSERT INTO documenti VALUES(201,2,'',1,'tesserati/2/beta.pdf','beta.pdf');
    """)
    def db():
        c=sqlite3.connect('file:a350_synthetic_family?mode=memory&cache=shared',uri=True)
        c.row_factory=sqlite3.Row
        return c
    def send_file(path,**kwargs):
        return {'filename':Path(path).name,'attachment':kwargs.get('as_attachment')}
    ns.update(Path=Path,db=db,abort=abort,send_file=send_file,get_workspace_media_dir=lambda:temp_root)
    ast.fix_missing_locations(node)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'a350_synthetic_doc_handler','exec'),ns)
    handler=ns['bodymind_doc']
    assert handler('A350_SYNTH_ALPHA',101)['filename']=='alpha.pdf'
    assert handler('A350_SYNTH_BETA',201)['filename']=='beta.pdf'
    for token,docid in [
        ('A350_SYNTH_ALPHA',201),('A350_SYNTH_BETA',101),
        ('A350_SYNTH_ALPHA',102),('A350_SYNTH_ALPHA',103),
        ('A350_NO_SUCH_USER',101),('A350_SYNTH_ALPHA',999)
    ]:
        try:
            handler(token,docid)
        except HTTPNotFound:
            pass
        else:
            raise AssertionError('synthetic family isolation failed')
    keeper.close()
    print('A350_TWO_FAMILIES_SYNTHETIC_DOC_ISOLATION_PASS')
    print('A350_HIDDEN_AND_NULL_VISIBILITY_DENIED_PASS')
    print('A350_UNKNOWN_TOKEN_AND_FOREIGN_DOCUMENT_DENIED_PASS')


def validate_upload(candidate_source,temp_root):
    """Exercise real handler AST only; filesystem is /tmp and DB is in-memory."""
    import types
    tree=ast.parse(candidate_source)
    defs=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='bodymind_upload']
    assert len(defs)==1,'upload route mismatch'
    node=copy.deepcopy(defs[0])
    node.decorator_list=[]
    class HTTPNotFound(Exception):
        pass
    def abort(status):
        raise HTTPNotFound(str(status))
    dbname='file:a350_synthetic_upload?mode=memory&cache=shared'
    keeper=sqlite3.connect(dbname,uri=True)
    keeper.executescript("""
    CREATE TABLE tesserati(id INTEGER PRIMARY KEY,online_token TEXT UNIQUE,
      email TEXT,email_genitore TEXT);
    CREATE TABLE documenti(id INTEGER PRIMARY KEY AUTOINCREMENT,tesserato_id INTEGER,
      titolo TEXT,categoria TEXT,filename TEXT,original_filename TEXT,
      data_caricamento TEXT,note TEXT,visibile INTEGER);
    INSERT INTO tesserati VALUES(1,'A350_SYNTH_ALPHA','synthetic@example.invalid','');
    INSERT INTO tesserati VALUES(2,'A350_SYNTH_BETA','synthetic@example.invalid','');
    """)
    def db():
        c=sqlite3.connect(dbname,uri=True)
        c.row_factory=sqlite3.Row
        return c
    class SyntheticFile:
        filename='sample.pdf'
        def save(self,dest):
            Path(dest).write_bytes(b'%PDF-SYNTHETIC-ONLY')
    request=types.SimpleNamespace(
      files={'file':SyntheticFile()},form={'categoria':'Documento','asdret':''},
      content_length=1024,method='POST')
    ns=dict(db=db,Path=Path,abort=abort,request=request,
      secure_filename=lambda name:name,
      get_workspace_media_dir=lambda:temp_root,
      now_iso_dt=lambda:'2026-10-26 12:00:00',
      now_iso_date=lambda:'2026-10-26',
      redirect=lambda url:url)
    ast.fix_missing_locations(node)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'a350_synthetic_upload','exec'),ns)
    handler=ns['bodymind_upload']
    url=handler('A350_SYNTH_ALPHA')
    assert isinstance(url,str) and '#documenti' in url
    own=keeper.execute('SELECT COUNT(*) FROM documenti WHERE tesserato_id=1').fetchone()[0]
    other=keeper.execute('SELECT COUNT(*) FROM documenti WHERE tesserato_id=2').fetchone()[0]
    assert own==1 and other==0,(own,other)
    before=keeper.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]
    try:handler('A350_SYNTH_BAD_TOKEN')
    except HTTPNotFound: pass
    else:raise AssertionError('forged family token allowed upload')
    after=keeper.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]
    assert before==after
    assert (temp_root/'tesserati'/'1').exists()
    keeper.close()
    print('A350_SYNTHETIC_UPLOAD_ONE_FAMILY_PASS')
    print('A350_SYNTHETIC_FOREIGN_TOKEN_UPLOAD_DENIED_PASS')
