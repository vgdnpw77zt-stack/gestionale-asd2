"""A261 layout integration smoke test from the *real* dashboard HTML template.
No prod DB, no network, no real customer data.
"""
from pathlib import Path
import ast, json, sys, subprocess, hashlib, shutil, tempfile, re
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
source=(ROOT/'routes_dashboard.py').read_text(encoding='utf-8')
tree=ast.parse(source)
html_assign=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='html' for t in n.targets) and isinstance(n.value,ast.JoinedStr))
assert 'a261-progressive-dashboard' in source
assert 'if total_actions == 0 else' in source
assert source.count('a261-more-button')>=3
# Real template constants, with all DB-backed expressions replaced by safe dummy placeholders.
body=''.join(n.value if isinstance(n,ast.Constant) else '0' for n in html_assign.value.values)
html='''<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body {margin:0; padding:0; min-width:0; background:#101720; color:#eef3fa; font-family:system-ui,sans-serif}
body {padding:16px} .pro-dashboard {width:100%;max-width:1480px;margin-inline:auto}
</style></head><body>'''+body+'</body></html>'
assert '<script id="a261-progressive-dashboard">' in html
from bs4 import BeautifulSoup
soup=BeautifulSoup(html,'html.parser')
root=soup.select_one('.pro-dashboard.a62-topfix-dashboard')
assert root is not None
assert len(root.select(':scope > section'))==6, len(root.select(':scope > section'))
assert len(root.select(':scope > button.a261-more-button'))==1
assert len(root.select('section.a260-today'))==1
checks=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for width,height in [(375,812),(390,844),(428,926),(768,1024),(1024,768),(1152,720),(1366,768),(1440,900),(1920,1080)]:
        page=browser.new_page(viewport={'width':width,'height':height})
        errors=[]
        page.on('pageerror',lambda exc:errors.append(str(exc)))
        page.set_content(html,wait_until='load')
        before=page.evaluate('''() => {
          const root=document.querySelector('.pro-dashboard.a62-topfix-dashboard');
          const children=[...root.children].filter(x=>x.matches('section'));
          const b=document.querySelector('#a261-more-button');
          return {compact:root.classList.contains('a261-compact'),expanded:b.getAttribute('aria-expanded'),label:b.textContent.trim(),oldVisible:children.slice(1).filter(x=>getComputedStyle(x).display!=='none').length,viewport:innerWidth,docScroll:document.documentElement.scrollWidth,
          cards:[...document.querySelectorAll('.a260-state')].map(x=>{const r=x.getBoundingClientRect();return [r.x,r.right,r.height]})};
        }''')
        assert before['compact'] and before['expanded']=='false' and before['oldVisible']==0,(width,before)
        assert before['docScroll']<=width+3,(width,before)
        assert all(x>=-2 and y<=width+3 and z>50 for x,y,z in before['cards']), (width,before)
        if width in (390,1152):page.screenshot(path=str(ROOT/f'a261_{width}_compact.png'),full_page=True)
        page.locator('#a261-more-button').click()
        after=page.evaluate('''() => {const root=document.querySelector('.pro-dashboard.a62-topfix-dashboard'),b=document.querySelector('#a261-more-button'); return {compact:root.classList.contains('a261-compact'),expanded:b.getAttribute('aria-expanded'),oldVisible:[...root.children].filter(x=>x.matches('section:not(.a260-today)')&&getComputedStyle(x).display!=='none').length}}''')
        assert not after['compact'] and after['expanded']=='true' and after['oldVisible']==5,(width,after)
        page.locator('#a261-more-button').click()
        assert page.locator('#a261-more-button').get_attribute('aria-expanded')=='false'
        assert not errors,(width,errors)
        checks.append({'viewport':f'{width}x{height}','compact_by_default':True,'legacy_sections_restored':after['oldVisible'],'overflow_compact_px':before['docScroll']-width,'errors':errors})
        page.close()
    browser.close()
print(json.dumps({'status':'PASS','source':'actual dashboard HTML template rendered with dummy values','screens':checks},ensure_ascii=False,indent=2))