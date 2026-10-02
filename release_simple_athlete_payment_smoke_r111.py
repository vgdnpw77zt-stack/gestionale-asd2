# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, sys
from html.parser import HTMLParser
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
import app as _full_app
from asd_app.core import app

class FormParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.forms=[]; self.cur=None; self.select=None; self.textarea=None
    def handle_starttag(self,tag,attrs):
        d={str(k).lower():str(v or '') for k,v in attrs}
        if tag=='form':
            self.cur={'action':d.get('action',''),'method':d.get('method','get').lower(),'fields':{}}
            self.forms.append(self.cur)
        elif self.cur and tag=='input':
            n=d.get('name','')
            if not n:return
            typ=d.get('type','text').lower()
            if typ in ('checkbox','radio') and 'checked' not in d:return
            self.cur['fields'][n]=d.get('value','on' if typ in ('checkbox','radio') else '')
        elif self.cur and tag=='select':
            self.select={'name':d.get('name',''),'value':''}
        elif self.cur and tag=='option' and self.select is not None:
            if 'selected' in d or self.select['value']=='':
                self.select['value']=d.get('value','')
        elif self.cur and tag=='textarea':
            self.textarea={'name':d.get('name',''),'buf':[]}
    def handle_data(self,data):
        if self.textarea is not None:self.textarea['buf'].append(data)
    def handle_endtag(self,tag):
        if tag=='select' and self.cur and self.select:
            if self.select['name']:self.cur['fields'][self.select['name']]=self.select['value']
            self.select=None
        elif tag=='textarea' and self.cur and self.textarea:
            if self.textarea['name']:self.cur['fields'][self.textarea['name']]=''.join(self.textarea['buf'])
            self.textarea=None
        elif tag=='form': self.cur=None

def pick_update_form(html):
    p=FormParser(); p.feed(html)
    for f in p.forms:
        if f['method']=='post' and f['fields'].get('action')=='update':
            return f
    for f in p.forms:
        if f['method']=='post' and 'corso' in f['fields']:
            return f
    return None

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    row=conn.execute("SELECT * FROM tesserati ORDER BY CASE WHEN id=45 THEN 0 ELSE 1 END,id LIMIT 1").fetchone()
    if not row: raise RuntimeError('no tesserati for R111')
    tid=int(row['id']); old_course=str(row['corso'] or ''); old_updated=str(row['updated_at'] or '') if 'updated_at' in row.keys() else ''
finally: conn.close()

app.config['TESTING']=True
client=app.test_client()
with client.session_transaction() as sess:
    sess['logged']=True; sess['username']='admin'; sess['display_name']='R111 QA'; sess['role']='admin'; sess['tenant_slug']='default'

desktop=client.get('/tesserati/'+str(tid)+'/scheda',headers={'User-Agent':'Mozilla/5.0 Macintosh Safari'},follow_redirects=False)
dhtml=desktop.get_data(as_text=True)
mobile=client.get('/mobile/atleta/'+str(tid),headers={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'},follow_redirects=False)
mhtml=mobile.get_data(as_text=True)
advanced=client.get('/tesserati/'+str(tid)+'/scheda?advanced=1',headers={'User-Agent':'Mozilla/5.0 Macintosh Safari'},follow_redirects=False)
ahtml=advanced.get_data(as_text=True)
form=pick_update_form(ahtml)
if not form:
    raise RuntimeError('R111 desktop advanced update form missing')
payload=dict(form['fields'])
payload['action']='update'
payload['ui_mode']='detail'
payload.setdefault('id',str(tid))
payload.setdefault('tesserato_id',str(tid))
sentinel=('R111-QA-'+str(tid))[:80]
payload['corso']=sentinel
post=None; restored_post=None; changed=False; restored=False; loc=''; restore_loc=''
try:
    post=client.post(form['action'] or '/tesserati',data=payload,headers={'User-Agent':'Mozilla/5.0 Macintosh Safari'},follow_redirects=False)
    loc=post.headers.get('Location','')
    c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
    try:
        fresh=c.execute('SELECT corso FROM tesserati WHERE id=?',(tid,)).fetchone()
        changed=bool(fresh and str(fresh['corso'] or '')==sentinel)
    finally:c.close()

    restore_payload=dict(payload); restore_payload['corso']=old_course
    restored_post=client.post(form['action'] or '/tesserati',data=restore_payload,headers={'User-Agent':'Mozilla/5.0 Macintosh Safari'},follow_redirects=False)
    restore_loc=restored_post.headers.get('Location','')
    c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
    try:
        fresh=c.execute('SELECT corso FROM tesserati WHERE id=?',(tid,)).fetchone()
        restored=bool(fresh and str(fresh['corso'] or '')==old_course)
    finally:c.close()
finally:
    if not restored:
        c=sqlite3.connect(str(DB),timeout=30)
        try:
            if old_updated:
                c.execute('UPDATE tesserati SET corso=?,updated_at=? WHERE id=?',(old_course,old_updated,tid))
            else:
                c.execute('UPDATE tesserati SET corso=? WHERE id=?',(old_course,tid))
            c.commit()
        finally:c.close()

c=sqlite3.connect(str(DB),timeout=30)
try:
    integrity=str(c.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(c.execute('PRAGMA foreign_key_check').fetchall())
    counts={t:int(c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('tesserati','pagamenti','quote_mensili','documenti','inbound_documents')}
    agg=int(c.execute("SELECT COUNT(*) FROM smart_alerts WHERE status='open' AND tipo='tesseramento_bloccato'").fetchone()[0])
finally:c.close()

labels=('Iscrizione','Mese','Modulo Unico','Certificato','Tutela')
_marker=dhtml.find('r110-page')
_ds=dhtml.rfind('<main',0,_marker+1) if _marker>=0 else -1
_de=dhtml.find('</main>',_marker) if _marker>=0 else -1
_simple_fragment=dhtml[_ds:_de+7] if _ds>=0 and _de>=0 else ''
checks={
 'desktop_200':desktop.status_code==200,
 'desktop_simple':'bodymind-r110-simple-desktop' in dhtml and all(x in dhtml for x in labels),
 'desktop_no_dossier_default':bool(_simple_fragment) and '/dossier' not in _simple_fragment.lower() and '>dossier<' not in _simple_fragment.lower(),
 'mobile_200':mobile.status_code==200,
 'mobile_simple':all(x in mhtml for x in labels) and '?advanced=1' in mhtml,
 'mobile_no_dossier_default':'Dossier' not in mhtml,
 'payment_link_scoped':('/pagamenti?tesserato_id='+str(tid)) in dhtml and ('/pagamenti?tesserato_id='+str(tid)) in mhtml,
 'advanced_200':advanced.status_code==200 and form is not None,
 'desktop_post_redirect':post is not None and post.status_code in (302,303) and loc.startswith('/tesserati'),
 'desktop_changed':changed,
 'desktop_restore_post':restored_post is not None and restored_post.status_code in (302,303),
 'desktop_restored':restored,
 'aggregate_alerts_zero':agg==0,
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r111-ui-payment-smoke] '+json.dumps({'tid':tid,'checks':checks,'post_location':loc,'restore_location':restore_loc,'counts':counts,'integrity':integrity,'fk':fk},ensure_ascii=False),flush=True)
bad=[k for k,v in checks.items() if not v]
if bad: raise RuntimeError('R111 QA failed '+repr(bad))
print('[r111-selftest] PASS simple desktop/mobile five-state truth real-desktop-post-readback-restore no-default-dossier db-ok',flush=True)
