"""A351 responsive synthetic-only film ribbon, private album CTA and dock checks."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
ASSET=ROOT/'bootstrap'
css=(ASSET/'family_a350_signature.css').read_text()+'\n'+(ASSET/'family_a351_sunrise.css').read_text()
old_js=(ASSET/'family_a350_verified_gallery.js').read_text()
new_js=(ASSET/'family_a351_sunrise.js').read_text()
token='A351_SYNTH_ALPHA_9283819283'
html='''<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}
html,body{margin:0;max-width:100%;overflow-x:clip}
.hero{height:auto;min-height:400px;position:relative;background:#0c2940;padding:25px 18px}
.hero-media{position:relative;width:220px;max-width:80vw;margin:0 auto}
.family-hero-video{display:block;width:100%;aspect-ratio:9/16;background:#061824}
.main{min-height:950px;padding:22px 14px;position:relative}
.media-track{display:flex;overflow-x:auto;gap:14px}
.media-card{flex:0 0 225px;margin:0}
.media-card img{display:block;width:100%;height:200px;object-fit:cover}
.bottom-nav{position:fixed;z-index:10;bottom:15px;left:10px;display:flex;align-items:center;justify-content:space-around;width:calc(100% - 20px);border-radius:20px;padding:8px;background:#0c2940}
.bottom-nav a{display:block;flex:1;color:white;text-align:center;min-height:48px}
</style><style>'''+css+'''</style></head><body>
<section class="hero"><div class="hero-media">
<video class="family-hero-video" muted playsinline></video></div>
<h1>Home sintetica</h1><a class="pill" href="#media">Vai alle foto</a></section>
<main class="main"><div class="stats">Le mie attività</div>
<section class="section" id="media"><h2>Le foto BodyMind</h2>
<div class="media-track" id="familyMediaTrack">
<figure class="media-card"><img src="/static/media/bodymind-competition-double.webp">
<figcaption><strong>Gara</strong></figcaption></figure>
<figure class="media-card"><img src="/bodymind-media/seconda.webp"><figcaption><strong>Allenamento</strong></figcaption></figure>
<figure class="media-card"><img src="/bodymind-media/terza.webp"><figcaption><strong>Spettacolo</strong></figcaption></figure>
</div>
<div class="bm350-gallery-footer"><a class="bm350-gallery-more" href="https://bodymindaerialstudio.life/#movimento">Esplora BodyMind</a></div>
</section><section id="pagamenti">Pagamenti sintetici</section></main>
<nav class="bottom-nav"><a href="#home">Home</a><a href="#media">Media</a><a href="#pagamenti">Pagamenti</a></nav>
<script>'''+old_js+'''</script><script>'''+new_js+'''</script>
</body></html>'''
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    for width,height in [(320,780),(375,812),(390,844),(430,932),(768,1024),(1024,768),(1440,900)]:
        page=browser.new_page(viewport={'width':width,'height':height})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(req):
            url=req.request.url
            if '/album/status' in url:
                req.fulfill(status=200,content_type='application/json',body='{"available":false,"url":null}')
            elif url.startswith('http://bodymind.test/app-tesserato/') and url.count('/')<=4:
                req.fulfill(status=200,content_type='text/html; charset=utf-8',body=html)
            else:
                req.fulfill(status=200,content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"/>')
        page.route('**/*',route)
        page.goto('http://bodymind.test/app-tesserato/'+token,wait_until='domcontentloaded')
        page.locator('.bm351-atmosphere').wait_for()
        assert not errors,(width,errors)
        assert page.locator('.bm351-atmosphere').get_attribute('aria-hidden')=='true'
        assert page.locator('#familyMediaTrack .media-card img').count()==3
        assert page.locator('#familyMediaTrack').evaluate('(e)=>getComputedStyle(e).scrollSnapType').startswith('x')
        assert page.locator('#familyMediaTrack .media-card').first.evaluate('(e)=>getComputedStyle(e,"::before").content')!='none'
        link=page.locator('a.bm351-private-album')
        assert link.count()==1 and link.get_attribute('href')=='/app-tesserato/'+token+'/album'
        nav=page.locator('.bottom-nav')
        toggle=page.locator('.bm351-dock-toggle')
        assert toggle.count()==1
        if width<=760:
            assert toggle.is_visible()
            toggle.click()
            assert nav.evaluate('(n)=>n.classList.contains("bm351-collapsed")')
            assert toggle.get_attribute('aria-expanded')=='false'
            toggle.click()
            assert not nav.evaluate('(n)=>n.classList.contains("bm351-collapsed")')
        scroll=page.evaluate('document.documentElement.scrollWidth')
        assert scroll<=width+3,(width,'horizontal overflow',scroll)
        # Re-running init must never append a second photo CTA.
        page.add_script_tag(content=new_js)
        assert page.locator('a.bm351-private-album').count()==1
        assert not errors,(width,errors)
        print('A351_CINEMATIC_CAROUSEL_AND_DOCK_PASS',width,height)
        page.close()
    browser.close()
