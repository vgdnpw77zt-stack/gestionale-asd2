# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, sqlite3
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r113_desktop_post')
BACK.mkdir(parents=True,exist_ok=True)

import sys
sys.path.insert(0,str(APP))
import app as _full_app
from asd_app.core import app

class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms=[]; self.cur=None; self.sel=None; self.textarea=None; self.textbuf=[]
    def handle_starttag(self,tag,attrs):
        d={str(k).lower():str(v or '') for k,v in attrs}
        t=tag.lower()
        if t=='form':
            self.cur={'action':d.get('action',''),'method':d.get('method','get').lower(),'data':{}}
            self.forms.append(self.cur)
        elif self.cur and t=='input':
            name=d.get('name','')
            if not name:return
            typ=d.get('type','').lower()
            if typ in ('checkbox','radio') and 'checked' not in {str(k).lower() for k,v in attrs}: return
            self.cur['data'][name]=d.get('value','1' if typ in ('checkbox','radio') else '')
        elif self.cur and t=='select':
            self.sel={'name':d.get('name',''),'value':'','first':''}
        elif self.cur and t=='option' and self.sel is not None:
            val=d.get('value','')
            if self.sel['first']=='': self.sel['first']=val
            if 'selected' in {str(k).lower() for k,v in attrs}: self.sel['value']=val
        elif self.cur and t=='textarea':
            self.textarea=d.get('name',''); self.textbuf=[]
    def handle_data(self,data):
        if self.textarea is not None:self.textbuf.append(data)
    def handle_endtag(self,tag):
        t=tag.lower()
        if t=='select' and self.cur and self.sel is not None:
            if self.sel['name']: self.cur['data'][self.sel['name']]=self.sel['value'] or self.sel['first']
            self.sel=None
        elif t=='textarea' and self.cur and self.textarea is not None:
            self.cur['data'][self.textarea]=''.join(self.textbuf)
            self.textarea=None; self.textbuf=[]
        elif t=='form': self.cur=None

def backup_db(label):
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    target=BACK/(stamp+'_'+label+'.db')
    src=sqlite3.connect(str(DB),timeout=45); dst=sqlite3.connect(str(target))
    try: src.backup(dst)
    finally: dst.close(); src.close()
    return str(target)

result={'tid':0,'backup':'','get_status':0,'post_status':0,'post_location':'',
        'changed':False,'restore_status':0,'restore_location':'','restored':False,
        'integrity':'','fk':None,'counts_before':{},'counts_after':{},'ok':False}

c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    row=c.execute("""SELECT * FROM tesserati
                     WHERE COALESCE(attivo,1)=1
                     ORDER BY CASE WHEN COALESCE(corso,'')<>'' THEN 0 ELSE 1 END,id DESC LIMIT 1""").fetchone()
    if not row: raise RuntimeError('R113 no athlete available')
    tid=int(row['id']); original_course=str(row['corso'] or '')
    result['tid']=tid
    for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
            result['counts_before'][t]=int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])
finally:c.close()

result['backup']=backup_db('pre_desktop_post')
client=app.test_client()
with client.session_transaction() as sess:
    sess.update({'logged':True,'username':'admin','display_name':'R113 QA','role':'admin','tenant_slug':'default'})

getr=client.get('/tesserati/'+str(tid)+'/scheda?advanced=1',follow_redirects=False)
result['get_status']=getr.status_code
parser=FormParser(); parser.feed(getr.get_data(as_text=True))
forms=[f for f in parser.forms if f['action'].split('?')[0]=='/tesserati' and f['method']=='post' and f['data'].get('action')=='update']
if not forms:
    raise RuntimeError('R113 desktop update form not found')
payload=dict(forms[0]['data'])
required=('csrf_token','action','id','nome','cognome','corso')
missing=[k for k in required if k not in payload]
if missing: raise RuntimeError('R113 missing form fields '+repr(missing))
if int(payload.get('id') or 0)!=tid: raise RuntimeError('R113 form athlete mismatch')

# Use the exact rendered form as truth, changing one innocent value to a genuinely different value.
original_form_course=str(payload.get('corso') or '')
if original_form_course != original_course:
    raise RuntimeError('R113 rendered course differs from DB before POST')
temp_course=(original_course+' · QA-R113').strip()
if temp_course==original_course: temp_course='QA-R113'
payload['corso']=temp_course
payload['ui_mode']='detail'
post=client.post('/tesserati',data=payload,follow_redirects=False)
result['post_status']=post.status_code; result['post_location']=post.headers.get('Location','')

c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    readback=c.execute('SELECT corso FROM tesserati WHERE id=?',(tid,)).fetchone()
    result['changed']=bool(readback and str(readback['corso'] or '')==temp_course)
finally:c.close()

# Restore through the same real POST path, not direct SQL.
restore_payload=dict(payload); restore_payload['corso']=original_course
restore=client.post('/tesserati',data=restore_payload,follow_redirects=False)
result['restore_status']=restore.status_code; result['restore_location']=restore.headers.get('Location','')

c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    rb=c.execute('SELECT corso FROM tesserati WHERE id=?',(tid,)).fetchone()
    result['restored']=bool(rb and str(rb['corso'] or '')==original_course)
    result['integrity']=str(c.execute('PRAGMA integrity_check').fetchone()[0])
    result['fk']=len(c.execute('PRAGMA foreign_key_check').fetchall())
    for t in result['counts_before']:
        result['counts_after'][t]=int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])
finally:c.close()

valid_redirect=result['post_status'] in (302,303) and (
    result['post_location'].startswith('/tesserati?') or
    result['post_location'].startswith('/tesserati/')
)
valid_restore_redirect=result['restore_status'] in (302,303)
result['ok']=all([
    result['get_status']==200, result['changed'], result['restored'],
    valid_redirect, valid_restore_redirect,
    result['integrity'].lower()=='ok', result['fk']==0,
    result['counts_before']==result['counts_after'],
])
print('[r113-desktop-post] '+json.dumps(result,ensure_ascii=False),flush=True)
if not result['ok']:
    raise RuntimeError('R113 desktop POST regression failed '+json.dumps(result,ensure_ascii=False))
print('[r113-selftest] PASS real-CSRF desktop-change DB-readback POST-restore redirect integrity/fk counts-stable',flush=True)
