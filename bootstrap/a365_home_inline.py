"""A365: show A364's existing monthly graph inside the Family Home (read-only).

No database/schema changes, no mutations to original attendance, no site changes.
The family token is resolved against the same tenant-local tesserati table as A364.
"""
import html
import re
import sqlite3
from datetime import date
from urllib.parse import quote
from flask import request

from a364_monthly_attendance import CSS, family_rows, parse_month, read_connection, render_family

HEADING = re.compile(r'<h4\b[^>]*\bid=[\'\"]presenze[\'\"][^>]*>.*?</h4>\s*', re.I | re.S)
MINI = re.compile(r'<div\b[^>]*\bclass=[\'\"][^\'\"]*\bmini-list\b[^\'\"]*[\'\"][^>]*>', re.I)
DIV = re.compile(r'<div\b[^>]*>|</div\s*>', re.I)


def find_old_list(page):
    matches=list(HEADING.finditer(page))
    if len(matches)!=1:return None
    begin=MINI.match(page,matches[0].end())
    if not begin:return None
    depth=0
    for tag in DIV.finditer(page,begin.start()):
        depth += -1 if tag.group().lower().startswith('</div') else 1
        if depth==0:return (matches[0].start(),tag.end())
    return None


def inline_family(month, athlete_name, rows, token):
    safe=quote(str(token),safe='')
    full=render_family(month,athlete_name,rows,token)
    start=full.find('<div class="bm364-family-shell">')
    end=full.find('</body></html>',start)
    if start<0 or end<0:raise ValueError('A364 monthly markup missing')
    section=full[start:end]
    # The month selector remains inside the Home rather than navigating away.
    source=f'action="/app-tesserato/{safe}/presenze"'
    target=f'action="/app-tesserato/{safe}#presenze"'
    if section.count(source)!=1:raise ValueError('A364 month selector anchor missing')
    section=section.replace(source,target,1)
    return '<div id="presenze" class="bm365-inline" data-bodymind-attendance="A365">'+section+'</div>'


OVERRIDES='''<style id="bm365-home-style">
.bm365-inline .bm364-family-shell{min-height:0;background:none;border:1px solid #4b7192;border-radius:20px}
.bm365-inline .bm364-family-main{padding:15px 12px 20px;max-width:none}
.bm365-inline .bm364-family-back{display:none!important}
.bm365-inline .bm364-family-intro{padding:3px 4px 0}
.bm365-inline .bm364-family-intro h1{font-size:clamp(22px,4vw,29px);margin:8px 0}
.bm365-inline .bm364-family-intro p{font-size:14px;margin:6px 0}
.bm365-inline .bm364-month-form{margin:12px 0;padding:10px}
.bm365-inline .bm364-family-summary{margin:14px 0;padding:15px;gap:12px}
.bm365-inline .bm364-family-summary h2{font-size:20px}
.bm365-inline .bm364-family-day{padding:11px;margin:8px 0}
@media(max-width:560px){.bm365-inline .bm364-month-form{gap:8px}.bm365-inline .bm364-month-form select{min-width:0;flex:1}.bm365-inline .bm364-family-summary{gap:10px}.bm365-inline .bm364-donut{width:98px}.bm365-inline .bm364-donut span{width:75px}.bm365-inline .bm364-donut b{font-size:19px}}
</style>'''


def install(app):
    def inject(response):
        if (request.method!='GET' or request.endpoint!='app_tesserato' or response.status_code!=200
                or response.mimetype!='text/html' or response.direct_passthrough):return response
        page=response.get_data(as_text=True)
        if 'data-bodymind-attendance="A365"' in page:return response
        span=find_old_list(page)
        if span is None:
            app.logger.warning('A365: original family attendance list not found')
            return response
        token=(request.view_args or {}).get('token')
        if not token:return response
        try:month=parse_month(request.args.get('mese'))
        except ValueError:month=date.today().replace(day=1)
        try:
            conn=read_connection()
            try:
                athlete=conn.execute('SELECT id,nome,cognome FROM tesserati WHERE online_token=?',(token,)).fetchone()
                if athlete is None:return response
                rows=family_rows(conn,int(athlete['id']),month)
                name=' '.join(x for x in (athlete['nome'] or '',athlete['cognome'] or '') if x)
            finally:conn.close()
            widget=inline_family(month,name,rows,token)
        except (sqlite3.Error,OSError,RuntimeError,ValueError) as e:
            app.logger.warning('A365: monthly read-only view not available: %s',type(e).__name__)
            return response
        new_page=page[:span[0]]+widget+page[span[1]:]
        new_page=new_page.replace('</head>',CSS+OVERRIDES+'\n</head>',1)
        response.set_data(new_page)
        response.headers['Cache-Control']='private, no-store, max-age=0'
        response.headers['X-BodyMind-Family-Attendance']='A365'
        response.headers.pop('ETag',None)
        return response
    # Execute last, after A362's sanitizer and A364's original link injection.
    app.after_request_funcs.setdefault(None,[]).insert(0,inject)
    print('BODYMIND A365 FAMILY MONTHLY GRAPH INLINE READY — read-only',flush=True)
