"""Offline Chromium smoke: A263 income-origin cards/table on mobile and desktop."""
from __future__ import annotations
from pathlib import Path
import importlib.util
from decimal import Decimal
from playwright.sync_api import sync_playwright
p=Path(__file__).parent.parent/'source/bodymind_a262_income_origin.py'
s=importlib.util.spec_from_file_location('origins_ui_a263',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
origin={
 'categories':{k:{'total':Decimal('100.00'),'count':2,'payers':1 if k!='movimenti_manuali' else None} for k,_ in o.CATEGORIES},
 'matrix':{k:{m:{'total':Decimal('50.00'),'count':1} for m,_ in o.METHODS} for k,_ in o.CATEGORIES},
 'discounts':{k:1 for k,_ in o.DISCOUNTS},
 'note':'Tariffe indicative, verificare causali.'}
html=f'''<!doctype html><html lang=it><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#101925;color:#fff;max-width:100vw"><main style="padding:12px;max-width:100%;box-sizing:border-box">{o.css()}{o.tiny(origin)}{o.render(origin)}</main></body></html>'''
checks=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (375,390,428,768,1024,1152,1366,1440,1920):
  page=b.new_page(viewport={'width':width,'height':844})
  page.set_content(html,wait_until='domcontentloaded')
  x=page.evaluate('({vw:window.innerWidth,sw:document.documentElement.scrollWidth,table:document.querySelector(".a262-table-wrap").scrollWidth,container:document.querySelector(".a262-table-wrap").clientWidth})')
  assert x['sw']<=x['vw']+1,(width,x)
  assert page.locator('.a262-origin-card').count()==4
  assert page.locator('.a262-teaser-grid>span').count()==4
  page.locator('.a262-analysis summary').click()
  assert page.locator('.a262-analysis').get_attribute('open') is not None
  checks.append({'width':width,'doc_scroll':x['sw'],'client':x['vw'],'table_internals_scroll':x['table']>x['container']})
  page.close()
 b.close()
print('A263 VISUAL PASS',checks)
