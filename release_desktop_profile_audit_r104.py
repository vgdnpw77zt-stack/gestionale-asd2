# -*- coding: utf-8 -*-
from __future__ import annotations
import inspect, json, re, sqlite3, sys
from html.parser import HTMLParser
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
import app as _full_app
from asd_app.core import app

class FormParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.forms=[]; self.current=None
    def handle_starttag(self,tag,attrs):
        d={str(k).lower():str(v or '') for k,v in attrs}
        if tag.lower()=='form':
            self.current={'action':d.get('action',''),'method':d.get('method','get').lower(),'fields':[]}
            self.forms.append(self.current)
        elif self.current and tag.lower() in ('input','select','textarea','button'):
            name=d.get('name','')
            if name:
                self.current['fields'].append({'tag':tag.lower(),'name':name,'type':d.get('type','')})
    def handle_endtag(self,tag):
        if tag.lower()=='form': self.current=None

routes=[]
for r in app.url_map.iter_rules():
    rule=str(r.rule)
    if 'tesserat' in rule.lower() or 'atlet' in rule.lower():
        if 'POST' in r.methods or '/scheda' in rule or rule in ('/tesserati','/mobile/atlete'):
            f=app.view_functions.get(r.endpoint)
            src=''
            try: src=inspect.getsource(f)
            except Exception: src=''
            routes.append({'rule':rule,'endpoint':r.endpoint,'methods':sorted(r.methods),'source':src[:14000]})

client=app.test_client()
with client.session_transaction() as sess:
    sess['logged']=True; sess['username']='admin'; sess['display_name']='R104 QA'; sess['role']='admin'; sess['tenant_slug']='default'

ua={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 Safari/605.1.15'}
tid=45
resp=client.get('/tesserati/'+str(tid)+'/scheda',headers=ua,follow_redirects=False)
html=resp.get_data(as_text=True)
p=FormParser(); p.feed(html)

runtime_file=APP/'asd_app/routes_tesserati.py'
snippet=''
if runtime_file.exists():
    txt=runtime_file.read_text(encoding='utf-8',errors='replace')
    pos=txt.find('def tesserato_scheda')
    if pos>=0:
        snippet=txt[max(0,pos-3000):pos+30000]

conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

obj={'desktop_get_status':resp.status_code,'desktop_location':resp.headers.get('Location',''),
     'forms':p.forms,'routes':routes,'tesserato_scheda_runtime':snippet,
     'integrity':integrity,'fk':fk}
print('[r104-desktop-profile-audit] '+json.dumps(obj,ensure_ascii=False,default=str),flush=True)
print('[r104-selftest] PASS read-only desktop-sheet form/route audit integrity='+integrity+' fk='+str(fk),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R104 DB integrity failed')
