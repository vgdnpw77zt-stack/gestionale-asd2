"""Visual geometry smoke tests using a synthetic, non-authenticated family shell.
Does not access any real family data. Actual authenticated screenshot still needed."""
from pathlib import Path
import base64
import zlib
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
css340=zlib.decompress(base64.b64decode((ROOT/'bootstrap/family_a340.css.zlib.base64').read_text().strip())).decode()
css341=(ROOT/'bootstrap/family_a341.css').read_text()
css342=(ROOT/'bootstrap/family_a342_motion.css').read_text()
css349=(ROOT/'bootstrap/family_a349_atelier.css').read_text()
html='''<!doctype html><html lang="it"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0}.hero{width:100%}.hero-content{pointer-events:none}
.bottom-nav{position:fixed;left:50%;transform:translateX(-50%);width:min(98%,540px);display:flex}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}
.stat{display:flex;flex-direction:column}
</style><style>'''+css340+'\n'+css341+'\n'+css342+'\n'+css349+'''</style></head><body>
<section class="hero">
<div class="hero-media"><video class="family-hero-video" width="720" height="1280" muted playsinline preload="none"></video><button class="hero-playback" aria-label="Pausa">Ⅱ</button></div>
<div class="hero-content"><div class="hero-intro">
<small class="kicker">AREA ALLIEVE &amp; FAMIGLIE</small><h1>Ciao GAIA,</h1>
<p>Qui trovi corsi, pagamenti, documenti e i momenti più belli del tuo percorso BodyMind.</p>
<a class="pill" href="#course">Scopri il tuo percorso →</a></div></div>
</section>
<main class="main"><div class="stats">
<a class="stat" id="course"><span class="icon">✧</span><small>Corso attuale</small><strong>ADULT 3/4</strong><em>Il tuo percorso</em></a>
<a class="stat"><span class="icon">€</span><small>Stato pagamenti</small><strong>Pagato</strong></a>
<a class="stat"><span class="icon">▤</span><small>Certificato medico</small><strong>Valido</strong></a>
<a class="stat"><span class="icon">✓</span><small>Prossimo evento</small><strong>1</strong></a>
</div></main>
<nav class="bottom-nav" aria-label="Menu principale">
<a aria-current="page"><span>⌂</span>Home</a>
<a><span>◯</span>Corsi</a>
<a><span>€</span>Pagamenti</a>
<a><span>▶</span>Video</a>
<a><span>▤</span>Documenti</a>
</nav>
</body></html>'''
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    for width,height in [(320,780),(375,812),(390,844),(430,932),(768,950),(1280,800)]:
        page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
        page.set_content(html,wait_until='domcontentloaded')
        page.evaluate("document.fonts.ready")
        bounds=page.evaluate('''() => {
           const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}};
           return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,
             hero:rect('.hero'),media:rect('.hero-media'),video:rect('.family-hero-video'),
             intro:rect('.hero-intro'),heading:rect('.hero h1'),cta:rect('.hero .pill'),
             nav:rect('.bottom-nav'),tabs:[...document.querySelectorAll('.bottom-nav a')].map(x=>{let r=x.getBoundingClientRect();return {x:r.x,right:r.right,width:r.width}}),
             course:rect('.stat:first-child'),next:rect('.stat:nth-child(2)')};
        }''')
        assert bounds['scrollWidth']<=width+2,(width,'document overflow',bounds)
        if width<=760:
            n=bounds['nav']
            assert n['x']>=-1 and n['right']<=width+1,(width,'nav cut',n)
            assert len(bounds['tabs'])==5 and all(t['width']>=42 for t in bounds['tabs']),(width,'tabs narrow',bounds['tabs'])
            m=bounds['media']; v=bounds['video']; h=bounds['heading']; c=bounds['cta']
            assert m['w']>220 and m['h']>220,(width,'media collapsed',m)
            assert abs(m['h']-v['h'])<=3,(width,'video letterboxed by frame',m,v)
            assert m['x']<=h['x'] and h['right']<=m['right']+1,(width,'heading outside image',m,h)
            assert m['x']<=c['x'] and c['right']<=m['right']+1,(width,'cta outside image',m,c)
            assert m['y']<=h['y'] and c['bottom']<=m['bottom']+5,(width,'welcome beyond video',m,h,c)
            assert bounds['course']['w']>bounds['next']['w'],(width,'course spotlight absent',bounds)
        page.screenshot(path=str(ROOT/f'a349_mock_{width}.png'),full_page=False)
        results.append(f'{width}x{height}: nav={bounds["nav"]["x"]:.0f}/{bounds["nav"]["right"]:.0f}; media={bounds["media"]["w"]:.0f}x{bounds["media"]["h"]:.0f}; h1={bounds["heading"]["w"]:.0f}; scroll={bounds["scrollWidth"]}')
        page.close()
    browser.close()
print('A349 RESPONSIVE BROWSER PASS')
print('\n'.join(results))
