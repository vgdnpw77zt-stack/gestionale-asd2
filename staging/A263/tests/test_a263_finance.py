"""Offline unit/integration: never attach production data, never execute DDL on live SQLite."""
from __future__ import annotations
import importlib, tempfile, shutil, sys, sqlite3, hashlib, re
from pathlib import Path
import os
from decimal import Decimal
SRC=Path(__file__).parent.parent/'source'
A253=Path(os.getenv('BODYMIND_A253_SOURCE','/no/external/source/available'))

def fixture(base):
    db=base/'test.db'
    c=sqlite3.connect(db); c.row_factory=sqlite3.Row
    c.executescript('''
    CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,importo NUMERIC,causale TEXT,stato TEXT,online_status TEXT,metodo_pagamento TEXT,note_pagamento TEXT);
    CREATE TABLE movimenti(id INTEGER PRIMARY KEY,importo NUMERIC,tipo TEXT,pagamento_id INTEGER,auto_generato INTEGER,data TEXT,categoria TEXT,descrizione TEXT);
    CREATE TABLE bodymind_uscite(id INTEGER PRIMARY KEY,importo NUMERIC,data TEXT,metodo TEXT);
    CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id INTEGER,annullata INTEGER);
    CREATE TABLE quote_mensili(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,importo_base NUMERIC,importo_dovuto NUMERIC,sconto NUMERIC,tariffa_codice TEXT,note TEXT);
    CREATE TABLE bodymind_quota_decisioni(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,decisione TEXT,importo_base NUMERIC,importo_dovuto NUMERIC,motivo TEXT);
    CREATE TABLE bodymind_a253_manual(movimento_id INTEGER PRIMARY KEY,metodo TEXT NOT NULL);
    ''')
    entries=[
    (1,1,9,2026,50,'iscrizione','paid_manual','paid_manual','contanti',''),
    (2,2,9,2026,25,'iscrizione','paid_manual','paid_manual','bonifico','sconto metà anno'),
    (3,3,10,2026,35,'mensile','paid_manual','paid_manual','contanti',''),
    (4,4,10,2026,35,'mensile','paid_manual','paid_manual','carta/SumUp','riduzione mezzo mese'),
    (5,5,10,2026,15,'mensile','paid_manual','paid_manual','contanti',''),
    (6,5,10,2026,10,'mensile_parziale_2','paid_manual','paid_manual','contanti',''),
    (7,4,11,2026,140,'mensile','annullato','annullato','bonifico',''),
    (8,2,10,2026,700,'mensile','unpaid','pending','contanti',''),
    (9,1,11,2026,0,'mensile','paid_manual','paid_manual','bonifico',''),
    ]
    c.executemany('INSERT INTO pagamenti VALUES (?,?,?,?,?,?,?,?,?,?)',entries)
    for pid in [1,2,3,4,5,6,7]:
        c.execute('INSERT INTO movimenti(id,importo,tipo,pagamento_id,auto_generato,data,categoria,descrizione) VALUES (?,?,"entrata",?,1,"2026-10-18","quota","")',(pid,entries[pid-1][4],pid))
    for pid in range(1,7):c.execute('INSERT INTO ricevute(id,pagamento_id,annullata) VALUES (?,?,0)',(pid,pid))
    c.execute('INSERT INTO ricevute(id,pagamento_id,annullata) VALUES (7,7,1)')
    c.execute('INSERT INTO movimenti VALUES (90,12,"entrata",NULL,0,"2026-10-18","Donazione","Contributo raccolta")')
    c.execute('INSERT INTO bodymind_a253_manual VALUES (90,"altro")')
    c.execute('INSERT INTO bodymind_uscite VALUES (1,5,"2026-10-18","contanti")')
    c.executemany('INSERT INTO quote_mensili VALUES (?,?,?,?,?,?,?,?,?)',[
        (1,3,10,2026,70,35,35,'sorelle','tariffa famiglia'),
        (2,4,10,2026,70,35,35,'standard','riduzione metà mese'),
        (3,5,10,2026,50,25,25,'standard','sconto metà mese'),
    ])
    c.commit();c.close()
    return db

def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);pkg=root/'asd_app';pkg.mkdir();(pkg/'__init__.py').write_text('')
        for name in ('bodymind_a237_finance_truth.py','bodymind_a262_income_origin.py'):shutil.copyfile(SRC/name,pkg/name)
        if A253.is_file():
            shutil.copyfile(A253,pkg/'bodymind_a253_manual.py')
        else:
            # Test-only mock of A253 read API, never included in production patch.
            (pkg/'bodymind_a253_manual.py').write_text("def methods(conn):\n    return {int(r[0]):str(r[1]) for r in conn.execute('SELECT movimento_id,metodo FROM bodymind_a253_manual')}\n",encoding='utf-8')
        sys.path.insert(0,str(root))
        try:
            mod=importlib.import_module('asd_app.bodymind_a237_finance_truth')
            db=fixture(root)
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            data=mod.snapshot(db)
            assert str(data['entrate'])=='182.00',data
            assert str(data['uscite'])=='5.00'
            assert str(data['saldo'])=='177.00'
            assert data['movimenti_attivi']==7
            assert data['movimenti_annullati']==1
            cats=data['origini_entrate']['categories']
            assert [(key,str(cats[key]['total']),cats[key]['count']) for key in cats]==[
                ('iscrizioni','75.00',2),('mensili','95.00',4),('altri_pagamenti','0.00',0),('movimenti_manuali','12.00',1)]
            assert cats['iscrizioni']['payers']==2, cats['iscrizioni']
            assert cats['mensili']['payers']==3, cats['mensili']
            assert cats['mensili']['periods']==3, cats['mensili']
            assert cats['movimenti_manuali']['payers'] is None
            d=data['origini_entrate']['discounts']
            assert d['iscr_meta_anno']==1,d
            assert d['mens_sorelle']==1,d
            assert d['mens_meta_mese']==2,d
            assert sum(d.values())==4,d
            assert data['origini_entrate']['discounted_month_periods']==3
            assert str(data['entrate_per_metodo']['contanti'])=='110.00'
            assert str(data['entrate_per_metodo']['bonifico'])=='25.00'
            assert str(data['entrate_per_metodo']['carta_pos_sumup'])=='35.00'
            assert str(data['entrate_per_metodo']['altro'])=='12.00'
            html=mod.finance_panel(data)
            assert 'Da dove arrivano le entrate' in html and 'Sorelle' not in html  # labels lowercase in translated UI
            assert 'Iscrizioni: sorelle / fratelli' in html
            assert '182,00 €' in html
            assert 'a262-origin-anchor' in html
            assert hashlib.sha256(db.read_bytes()).hexdigest()==before,'Database mutated'
            # Full A261 top-card anchor is augmented without removing advanced controls.
            page='<html><body><div class="pro-dashboard a62-topfix-dashboard a261-compact"><section class="a260-today"><div class="a260-state-grid"></div>\n      </section>\n\n      <!-- A261 advanced controls toggle: all existing panels remain in the DOM. -->\n<button id="a261-more-button">More</button></div></body></html>'
            new,ok=mod.inject_dashboard(page,data)
            assert ok and 'a262-teaser' in new and 'Mostra altri controlli' not in new
            assert 'a262-show-details' in new and 'bodymind-a237-finance-client' in new
            assert new.count('class="a262-teaser-grid"')==1 # only one markup injection
            # reconciliation mismatch must fail closed
            c=sqlite3.connect(db);c.execute('UPDATE movimenti SET importo=51 WHERE id=1');c.commit();c.close()
            try: mod.snapshot(db)
            except ValueError as exc:assert 'incongruenza' in str(exc).lower()
            else:raise AssertionError('Expected fail-closed mismatch')
            print('A263 PASS: audit counts, partial monthly, method matrix, void filters, HTML, anchors, DB untouched, fail-closed')
        finally:sys.path.remove(str(root))
if __name__=='__main__':main()
