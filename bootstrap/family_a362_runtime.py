"""A362 family-only in-memory presentation. No DB, media or volume writes."""
import hashlib
import re
from pathlib import Path
from flask import request

SOURCE_SHA='35afdadb806a9ad1f22188e7f20439356f7282dad3adb4fc867554485ee4f686'
TEMPLATE_SHA='fc3510cb80b965a47360a70465cfeeb99032004f44dc81d143eb01b0b6692156'
ASSETS=Path(__file__).parent
SKY='''<div class="bm362-sky" aria-hidden="true"><div class="bm362-cloud"></div><div class="bm362-cloud bm362-cloud--near"></div><div class="bm362-stars"></div><svg class="bm362-waves" viewBox="0 0 800 400" preserveAspectRatio="none"><path d="M-100 270 Q160 70 380 270 T900 190"/><path d="M-100 310 Q140 100 390 280 T900 230"/><path d="M-100 330 Q190 150 410 305 T900 240"/></svg></div>'''
STUDIO='''<section class="bm362-studio"><div><strong>I miei momenti in volo</strong><p>Le tue foto, una colonna sonora e un film tutto tuo.</p></div><a class="pill" href="/app-tesserato/{{token}}/studio">Crea il mio film →</a></section>'''

def compose(portal, verify=True):
    if verify and hashlib.sha256(portal.encode()).hexdigest()!=TEMPLATE_SHA:
        raise RuntimeError('A362 family template differs from verified A361; refusing replacement')
    css=(ASSETS/'family_a362_base.css').read_text()+'\n'+(ASSETS/'family_a362_scene.css').read_text()
    portal,count=re.subn(r'<style>.*?</style>','<style id="bm362-style">'+css+'</style>',portal,count=1,flags=re.S)
    assert count==1
    # Preserve gallery link authorization, carousel, native playback, uploads and PWA.
    gallery=re.search(r'<script id="bodymind-media-links-a350">(.*?)</script>',portal,re.S).group(1)
    gallery=gallery.split('/* BODYMIND A351 DOCK */',1)[0]
    portal=re.sub(r'<script id="bodymind-media-links-a350">.*?</script>','<script id="bm362-gallery">'+gallery+'</script>',portal,count=1,flags=re.S)
    for ident in ('bodymind-a345-video','bodymind-a349-native-ratio'):
        portal=re.sub(r'<script id="'+ident+r'">.*?</script>','',portal,flags=re.S)
    assert portal.count('<script>')==1
    portal=portal.replace('<script>','<script id="bm362-controls">',1)
    anchor='<section class="hero" id="top" aria-labelledby="heroTitle">'
    assert portal.count(anchor)==1
    portal=portal.replace(anchor,anchor+SKY,1)
    portal=portal.replace('<main class="frame main">','<main class="frame main">'+STUDIO,1)
    portal=portal.replace('<body>','<body data-bodymind-family="A362">',1)
    nav=(ASSETS/'family_a362_navigation.js').read_text()
    portal=portal.replace('</body>','<script id="bm362-navigation">'+nav+'</script></body>',1)
    return portal

# Only standalone family Home HTML is isolated. Admin/album/doc routes are untouched.
def clean_response_markup(html):
    if 'data-bodymind-family="A362"' not in html:
        return html
    def keep_style(m):
        return m.group(0) if re.search(r'\bid=[\'"]bm362-style[\'"]',m.group(0).split('>',1)[0]) else ''
    def keep_script(m):
        head=m.group(0).split('>',1)[0]
        return m.group(0) if re.search(r'\bid=[\'"]bm362-(gallery|controls|navigation)[\'"]',head) else ''
    html=re.sub(r'<style\b[^>]*>.*?</style>',keep_style,html,flags=re.S|re.I)
    html=re.sub(r'<script\b[^>]*>.*?</script>',keep_script,html,flags=re.S|re.I)
    html=re.sub(r'<link\b[^>]*\brel=[\'"]stylesheet[\'"][^>]*>','',html,flags=re.I)
    html=re.sub(r'(<body\b[^>]*?)\sclass=[\'"][^\'"]*[\'"]',r'\1',html,count=1,flags=re.I)
    return html

def install(app,portal_module):
    source=Path(portal_module.__file__).read_bytes()
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:
        raise RuntimeError('A362 live source differs from audited A361')
    portal_module.PORTAL=compose(portal_module.PORTAL)
    def finish(response):
        if request.endpoint!='app_tesserato' or response.status_code!=200 or response.mimetype!='text/html' or response.direct_passthrough:
            return response
        response.set_data(clean_response_markup(response.get_data(as_text=True)))
        response.headers['X-BodyMind-Family-Release']='A362'
        response.headers['Cache-Control']='private, no-store'
        response.headers.pop('ETag',None)
        return response
    # Flask executes after_request in reverse order: this runs after global injections.
    app.after_request_funcs.setdefault(None,[]).insert(0,finish)
    # Retire old diagnostic collection; retain the application's existing CSRF guard.
    if '_bm361_measure' in app.view_functions:
        app.view_functions['_bm361_measure']=lambda:('',410)
    print('BODYMIND A362 FAMILY PRESENTATION READY; in-memory only; A361 volume unchanged',flush=True)
