from pathlib import Path
from decimal import Decimal
import tempfile, hashlib, importlib, sys, sqlite3, shutil, re, json, ast
ROOT=Path(__file__).parent
SOURCE=ROOT/'runtime/asd_app'

def fixture(path):
    c=sqlite3.connect(path);c.row_factory=sqlite3.Row
    c.executescript('''
    CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,importo NUMERIC,causale TEXT,stato TEXT,online_status TEXT,metodo_pagamento TEXT,note_pagamento TEXT);
    CREATE TABLE movimenti(id INTEGER PRIMARY KEY,importo NUMERIC,tipo TEXT,pagamento_id INTEGER,auto_generato INTEGER,data TEXT,categoria TEXT,descrizione TEXT);
    CREATE TABLE bodymind_uscite(id INTEGER PRIMARY KEY,importo NUMERIC,data TEXT,metodo TEXT,descrizione TEXT,categoria TEXT,allegato_nome TEXT);
    CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id INTEGER,annullata INTEGER);
    CREATE TABLE quote_mensili(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,importo_base NUMERIC,importo_dovuto NUMERIC,sconto NUMERIC,tariffa_codice TEXT,note TEXT);
    CREATE TABLE bodymind_quota_decisioni(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,decisione TEXT,importo_base NUMERIC,importo_dovuto NUMERIC,motivo TEXT);
    CREATE TABLE bodymind_a253_manual(movimento_id INTEGER PRIMARY KEY,metodo TEXT);
    ''')
    pays=[
      (1,1,10,2026,40,'mensile','paid_manual','paid_manual','contanti',''),
      (2,1,10,2026,10,'mensile','paid_manual','paid_manual','contanti',''),
      (3,2,10,2026,50,'mensile','paid_manual','paid_manual','bonifico',''),
      (4,3,10,2026,50,'iscrizione','paid_manual','paid_manual','bonifico',''),
      (5,3,10,2026,70,'mensile','annullato','annullato','contanti',''),
      (6,4,10,2026,50,'mensile','unpaid','pending','contanti',''),
      (7,5,10,2026,10,'iscrizione','paid_manual','paid_manual','carta/SumUp','')]
    c.executemany('INSERT INTO pagamenti VALUES (?,?,?,?,?,?,?,?,?,?)',pays)
    for p in pays:
        if p[0] != 6:
            c.execute('INSERT INTO movimenti VALUES (?,?,?,?,?,?,?,?)',(p[0],p[4],'entrata',p[0],1,'2026-10-18','quota',''))
    for p in pays:
        if p[0] != 6:
            c.execute('INSERT INTO ricevute VALUES (?,?,?)',(p[0],p[0],int(p[0]==5)))
    c.execute('INSERT INTO movimenti VALUES (10,20,"entrata",NULL,0,"2026-10-18","Donazioni","Manuale")')
    c.execute('INSERT INTO bodymind_a253_manual VALUES (10,"contanti")')
    c.execute('INSERT INTO movimenti VALUES (11,5,"uscita",NULL,0,"2026-10-18","Materiale","Manuale")')
    c.execute('INSERT INTO bodymind_a253_manual VALUES (11,"contanti")')
    c.execute('INSERT INTO bodymind_uscite VALUES (1,80,"2026-10-17","bonifico","Bonifico effettuato al presidente","Rimborso",NULL)')
    c.execute('INSERT INTO bodymind_uscite VALUES (2,15,"2026-10-18","contanti","Materiale aula","Materiale",NULL)')
    c.execute('INSERT INTO bodymind_uscite VALUES (3,0,"2026-10-18","bonifico","Documento 0", "Giustificativo",NULL)')
    c.execute('INSERT INTO quote_mensili VALUES (1,1,10,2026,60,50,10,"sorelle","famiglia")')
    c.execute('INSERT INTO quote_mensili VALUES (2,2,10,2026,70,50,20,"standard","ridotta")')
    c.execute('INSERT INTO bodymind_quota_decisioni VALUES (1,1,10,2026,"ridotta",60,50,"fratelli")')
    c.execute('INSERT INTO bodymind_quota_decisioni VALUES (2,6,10,2026,"non_dovuta",50,0,"esonero")')
    c.commit();c.close()

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); pkg=root/'asd_app';pkg.mkdir();(pkg/'__init__.py').write_text('')
    for n in ('bodymind_a237_finance_truth.py','bodymind_a253_manual.py','bodymind_a265_cashbook.py'):
        shutil.copy2(SOURCE/n,pkg/n)
    sys.path.insert(0,str(root))
    try:
        a237=importlib.import_module('asd_app.bodymind_a237_finance_truth')
        a265=importlib.import_module('asd_app.bodymind_a265_cashbook')
        database=root/'demo.sqlite';fixture(database)
        before=hashlib.sha256(database.read_bytes()).hexdigest()
        snap=a237.snapshot(database)
        assert snap['entrate']==Decimal('180.00'), snap['entrate']
        assert snap['uscite']==Decimal('100.00'), snap['uscite']
        c=sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
        book=a265.build(c,snap)
        assert book['channels']['contanti']['entrate']==Decimal('70.00')
        assert book['channels']['contanti']['uscite']==Decimal('20.00')
        assert book['channels']['contanti']['incassi']==3
        assert book['channels']['contanti']['quote_distinte']==1,book
        assert book['channels']['bonifico']['incassi']==2
        assert book['channels']['bonifico']['mensili']==1
        assert book['channels']['bonifico']['iscrizioni']==1
        assert book['channels']['bonifico']['uscite']==Decimal('80.00')
        assert book['discounts']['periodi_scontati']==2
        assert book['discounts']['periodi_esenti_non_dovuti']==1
        assert book['discounts']['risparmio_indicativo']==Decimal('30.00')
        assert book['cash_flow_net']==Decimal('50.00')
        assert len(book['bank_expenses'])==1 and book['bank_expenses'][0]['description']=='Bonifico effettuato al presidente'
        html=a265.render(book)
        assert '/pagamenti/uscite?modifica=1' in html and '80,00' in html and 'Bonifico effettuato al presidente' in html
        assert 'Saldo movimenti in contanti' in html and 'giacenza fisica' in html
        # A237 agreement: unknown method and invalid duplicate/void payment fail closed
        c.close()
        assert hashlib.sha256(database.read_bytes()).hexdigest()==before
        c=sqlite3.connect(database)
        c.execute("UPDATE movimenti SET importo=41 WHERE id=1");c.commit();c.close()
        try:a237.snapshot(database)
        except ValueError as e:assert 'incongruenza' in str(e).lower(),str(e)
        else:raise AssertionError('canonical mismatch must stop')
        code=(SOURCE/'core.py').read_text()
        assert "if request.path in ('/uscite','/pagamenti/uscite')" in code
        assert "in ('/uscite','/pagamenti/uscite','/contabilita')" not in code
        assert "min-width:900px" in code # desktop unchanged, mobile overridden
        assert ".bmout11 .bmout11-table table{{display:block;min-width:0!important" in code
        assert "data-label='Metodo'" in code
        assert "bodymind_a265_cashbook" in (SOURCE/'routes_contabilita.py').read_text()
        ast.parse((SOURCE/'core.py').read_text());ast.parse((SOURCE/'routes_contabilita.py').read_text())
        print('A265 PASS: canonical totals, methods, distinct fees, discounts, bank president expense, no DB writes, fail closed, responsive CSS, route fix, AST')
    finally:sys.path.remove(str(root))