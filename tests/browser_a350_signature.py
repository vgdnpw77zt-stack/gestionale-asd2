"""A350 Chromium synthetic browser QA. No real account, session, DB or documents."""
from pathlib import Path
import base64
import zlib
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'bootstrap'
css340=zlib.decompress(base64.b64decode((B/'family_a340.css.zlib.base64').read_text().strip())).decode()
css='\n'.join([css340]+[(B/f).read_text() for f in (
    'family_a341.css','family_a342_motion.css',
    'family_a349_atelier.css','family_a350_signature.css')])
gallery_js=(B/'family_a350_verified_gallery.js').read_text()
ratio_js=(B/'family_a349_native_ratio.js').read_text()
html='''<!doctype html><html lang="it"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0}
.hero{width:100%}
.hero-content{pointer-events:none}
.bottom-nav{position:fixed;left:50%;transform:translateX(-50%);width:min(98%,540px);display:flex}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}
.stat{display:flex;flex-direction:column}
.media-track{display:flex;overflow-x:auto;gap:12px}
.media-card{flex:0 0 230px}
</style><style>'''+css+'''</style></head><body>
<section class="hero"><div class="hero-media">
<video class="family-hero-video" width="720" height="1280" muted playsinline preload="none"></video>
<button class="hero-playback" aria-label="Pausa video">II</button>
</div><div class="hero-content"><div class="hero-intro">
<small class="kicker">AREA FAMIGLIE - TEST SINTETICO</small>
<h1>Ciao, famiglia demo</h1>
<p>Le informazioni qui sotto sono fittizie e NON sono dati di produzione.</p>
<a class="pill" href="#corsi">Scopri il percorso</a>
</div></div></section>
<main class="main">
<div class="stats">
<a class="stat" href="#corsi"><span class="icon">1</span><small>Corso</small><strong>Demo</strong></a>
<a class="stat" href="#pagamenti"><span class="icon">2</span><small>Pagamenti</small><strong>Da verificare</strong></a>
<a class="stat" href="#documenti"><span class="icon">3</span><small>Certificato</small><strong>Da verificare</strong></a>
<a class="stat" href="#documenti"><span class="icon">4</span><small>Documenti</small><strong>Da verificare</strong></a>
</div>
<section class="section" id="media">
<h2>Vivi BodyMind</h2><div id="familyMediaTrack" class="media-track">
<figure class="media-card"><img src="/static/media/bodymind-competition-double.webp">
<figcaption><strong>Fotografia uno</strong></figcaption></figure>
<figure class="media-card"><img src="/bodymind-media/gallery_2">
<figcaption><strong>Fotografia due</strong></figcaption></figure>
<figure class="media-card"><img src="https://untrusted.example/static/media/bodymind-competition-double.webp">
<figcaption><strong>Fotografia sospetta</strong></figcaption></figure>
<figure class="media-card"><img src="https://bodymindaerialstudio.life/static/media/bodymind-competition-double.webp">
<figcaption><strong>Competizione ufficiale</strong></figcaption></figure>
</div></section>
<section id="corsi" class="section">Corso sintetico</section>
<section id="pagamenti" class="section">Pagamento sintetico</section>
<section id="documenti" class="section">Documenti sintetici</section>
</main>
<nav class="bottom-nav" aria-label="Navigazione principale">
<a aria-current="page" href="#"><span>H</span>Home</a>
<a href="#corsi"><span>C</span>Corsi</a>
<a href="#pagamenti"><span>P</span>Pagamenti</a>
<a href="#media"><span>V</span>Video</a>
<a href="#documenti"><span>D</span>Documenti</a>
</nav>
<script>'''+ratio_js+'''</script>
<script>'''+gallery_js+'''</script>
</body></html>'''

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    for width,height in [(320,780),(375,812),(390,844),(430,932),
                         (768,1024),(1024,768),(1440,900)]:
        page=browser.new_page(viewport={'width':width,'height':height})
        errors=[]
        page.on('pageerror',lambda err: errors.append(str(err)))
        def handler(route):
            if route.request.url.rstrip('/')=='http://bodymind.test':
                route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html)
            else:
                route.fulfill(status=200,content_type='image/svg+xml',
                  body='<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"><rect width="300" height="450" fill="#645377"/></svg>')
        page.route('**/*',handler)
        page.goto('http://bodymind.test/',wait_until='domcontentloaded')
        page.locator('.bm350-gallery-footer').wait_for()
        assert not errors,(width,'JavaScript error',errors)
        assert page.locator('.bottom-nav a').count()==5
        assert page.locator('.media-card a.bm350-media-link').count()==2
        assert page.locator('.media-card').nth(1).locator('a').count()==0
        assert page.locator('.media-card').nth(2).locator('a').count()==0
        assert page.locator('.media-card').nth(3).locator('a.bm350-media-link').count()==1
        reel=page.locator('.bm350-media-link')
        assert reel.get_attribute('href')=='https://www.instagram.com/reel/DIHPtAbsg7B/'
        assert reel.get_attribute('rel')=='noopener noreferrer'
        assert reel.get_attribute('target')=='_blank'
        assert page.locator('.bm350-gallery-more').get_attribute('href')=='https://bodymindaerialstudio.life/#movimento'
        assert page.locator('.media-card img').nth(0).get_attribute('alt')=='Fotografia uno'
        dims=page.evaluate('''() => ({
          viewport:innerWidth,scroll:document.documentElement.scrollWidth,
          nav:(()=>{let x=document.querySelector('.bottom-nav').getBoundingClientRect();return {left:x.left,right:x.right}})(),
          targets:[...document.querySelectorAll('.bottom-nav a')].map(e=>e.getBoundingClientRect().width),
          gallery:document.querySelector('.bm350-gallery-more').getBoundingClientRect().height
        })''')
        assert dims['scroll']<=width+2,(width,'horizontal overflow',dims)
        assert dims['gallery']>=43,(width,'gallery action too small',dims)
        if width<=760:
            assert dims['nav']['left']>=-1 and dims['nav']['right']<=width+1,(width,'nav clipped',dims)
            assert min(dims['targets'])>=42,(width,'nav target too narrow',dims)
        aspect=page.evaluate('''() => {
          const v=document.querySelector('.family-hero-video');
          Object.defineProperty(v,'videoWidth',{configurable:true,value:480});
          Object.defineProperty(v,'videoHeight',{configurable:true,value:640});
          v.dispatchEvent(new Event('loadedmetadata'));
          return v.style.getPropertyValue('--bm349-film-ratio');
        }''')
        assert aspect=='480 / 640',(width,'portrait metadata',aspect)
        page.add_script_tag(content=gallery_js)
        assert page.locator('.bm350-gallery-footer').count()==1,(width,'duplicate gallery action')
        page.screenshot(path=str(ROOT/f'a350_synthetic_{width}.png'))
        print(f'A350 SYNTHETIC CHROMIUM PASS {width}x{height} scroll={dims["scroll"]} nav={dims["nav"]} gallery-button={dims["gallery"]:.1f}px')
        page.close()
    browser.close()
