"""A264 integration tests. All data synthetic, no production connection."""
from __future__ import annotations
import importlib, importlib.util, tempfile, shutil, sys, sqlite3, hashlib
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright

HERE=Path(__file__).parent.parent
A263_TEST=Path('/mnt/data/a263_release/tests/test_a263_finance.py')

def run():
 with tempfile.TemporaryDirectory(prefix='bodymind-a264-') as td:
  root=Path(td);pkg=root/'asd_app';pkg.mkdir();(pkg/'__init__.py').write_text('')
  for n in ('bodymind_a237_finance_truth.py','bodymind_a262_income_origin.py'):
   shutil.copyfile(HERE/'source'/n,pkg/n)
  (pkg/'bodymind_a253_manual.py').write_text("def methods(conn):\n    return {int(x[0]):str(x[1]) for x in conn.execute('SELECT movimento_id,metodo FROM bodymind_a253_manual')}\n")
  sys.path.insert(0,str(root))
  try:
   x=importlib.util.spec_from_file_location('a263fixture',A263_TEST)
   mod_fixture=importlib.util.module_from_spec(x);x.loader.exec_module(mod_fixture)
   db=mod_fixture.fixture(root)
   original=hashlib.sha256(db.read_bytes()).hexdigest()
   finance=importlib.import_module('asd_app.bodymind_a237_finance_truth')
   data=finance.snapshot(db)
   assert str(data['entrate'])=='182.00'
   # A263 layout: original legacy sections are hidden; finance must be *inside* a260-today.
   page='''<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    html body #bodymind-secretariat-home.pro-dashboard > section:not(.a260-today) {display:none!important}
    body{margin:0;background:#0e1a2a;color:white}section.a260-today{padding:16px;box-sizing:border-box}
    </style><!-- BODYMIND_A263_SIMPLE_SECRETARIAT --></head><body>
    <div id="bodymind-secretariat-home" class="pro-dashboard a62-topfix-dashboard">
      <section class='a260-today'><h2>Segreteria oggi</h2><div class="a260-state-grid">Da fare · In scadenza · Tutto in regola</div>
      </section>

      <section class='a3-command-hero a6-command-hero'>Vecchie sezioni tecniche e timeline non visibili</section>
    </div></body></html>'''
   html,done=finance.inject_dashboard(page,data)
   assert done and 'a264-finance-details' in html and 'a264-fin-stats' in html
   assert html.index('a264-finance-details')<html.index("<section class='a3-command-hero")
   assert html.count('a262-teaser-grid')>=1 and '75,00 €' in html and '95,00 €' in html
   assert 'Metodi di incasso, iscrizioni, mensili e sconti' in html
   assert hashlib.sha256(db.read_bytes()).hexdigest()==original
   js_errors=[]
   widths=(375,390,428,768,1024,1152,1280,1366,1440,1920)
   with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for width in widths:
     v=b.new_page(viewport={'width':width,'height':844})
     v.on('pageerror',lambda exc:js_errors.append(str(exc)))
     v.set_content(html,wait_until='domcontentloaded')
     info=v.evaluate('({w:window.innerWidth,s:document.documentElement.scrollWidth})')
     assert info['s']<=info['w']+1,(width,info)
     assert v.locator('.a264-finance-wrap').is_visible()
     assert not v.locator(".a3-command-hero").is_visible()
     assert v.locator('#a264-finance-details').get_attribute('open') is None
     v.locator('#a262-show-details').click()
     assert v.locator('#a264-finance-details').get_attribute('open') is not None
     assert v.locator('.a262-analysis').get_attribute('open') is not None
     v.close()
    b.close()
   assert not js_errors,js_errors
   # If A237 cannot reconcile, the error must be placed inside visible A263 dashboard.
   class App:
    def after_request(self,fn):self.fn=fn;return fn
   class Resp:
    status_code=200;content_type='text/html'
    def __init__(self,txt):self.txt=txt;self.headers={}
    def get_data(self,as_text=False):return self.txt
    def set_data(self,txt):self.txt=txt
   app=App();req=SimpleNamespace(path='/',method='GET')
   finance.install({'app':app,'request':req})
   finance.snapshot=lambda db: (_ for _ in ()).throw(ValueError('fixture mismatch'))
   out=app.fn(Resp(page))
   assert out.headers.get('X-BodyMind-Finance-Panel')=='review-needed',out.headers
   assert out.txt.index('Contabilità da verificare')<out.txt.index("<section class='a3-command-hero")
   assert 'Contabilità da verificare' in out.txt
   print('A264 PASS: revenue breakdown in visible A263 dashboard, 10 responsive viewports, dropdown, no JS errors, visible fail-closed warning, synthetic DB unchanged')
  finally:
   sys.path.remove(str(root))

if __name__=='__main__':run()
