"""A352 real-target selector synthetic Chromium test with seven viewports and interaction."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
ASSET=ROOT/'bootstrap'
css='\n'.join((ASSET/x).read_text() for x in
 ['family_a350_signature.css','family_a351_sunrise.css','family_a352_visible_atmosphere.css'])
javascript='\n'.join((ASSET/x).read_text() for x in
 ['family_a350_verified_gallery.js','family_a351_sunrise.js','family_a352_visible_atmosphere.js'])
token='A352_FAKE_TEST_1800200200'
html="""<!doctype html><html lang='it'><head><meta name='viewport' content='width=device-width,initial-scale=1'>
<style>html,body{margin:0;max-width:100%;overflow-x:clip}*{box-sizing:border-box}
.hero{height:600px;position:relative;background:linear-gradient(100deg,#12334a,#103d48);overflow:hidden}
.hero-media{height:450px;width:250px;position:relative;margin:auto}
.family-hero-video{display:block;width:100%;height:100%;aspect-ratio:9/16;background:#070e18}
.hero-content{position:relative}main.main{position:relative;min-height:1450px;padding:20px 12px}
.media-track{display:flex;overflow-x:auto;gap:16px}.media-card{flex:0 0 230px;background:#333;margin:0}
.media-card img{width:100%;height:220px;object-fit:cover;display:block}
.bottom-nav{position:fixed;bottom:15px;left:5%;width:90%;display:flex;z-index:20;background:#11394c;border-radius:20px}
.bottom-nav a{flex:1;min-height:48px;display:flex;align-items:center;justify-content:center;color:white}
</style><style>"""+css+"""</style></head><body>
<section class='hero' id='top'><div class='hero-media'>
<video id='familyHeroVideo' class='family-hero-video' muted autoplay playsinline></video></div>
<div class='frame hero-content'><h1>BodyMind</h1></div></section>
<main class='frame main'><div class='stats'>Attività</div>
<section id='media' class='section'><div class='media-track' id='familyMediaTrack'>
<figure class='media-card'><img src='/first.webp'><figcaption>Gara</figcaption></figure>
<figure class='media-card'><img src='/second.webp'><figcaption>Allenamento</figcaption></figure>
<figure class='media-card'><img src='/third.webp'><figcaption>Spettacolo</figcaption></figure>
</div><div class='bm350-gallery-footer'><a href='#media'>Galleria</a></div></section>
<section class='section' id='pagamenti'>Pagamenti</section>
</main><nav class='bottom-nav'><a href='#top'>Home</a><a href='#media'>Foto</a><a href='#pagamenti'>Pagamenti</a></nav>
<script>"""+javascript+"""</script></body></html>"""

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    for width,height in [(320,780),(375,812),(390,844),(430,932),(768,1024),(1024,768),(1440,900)]:
        page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='no-preference')
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(req):
            url=req.request.url
            if url.endswith('/album/status'):
                req.fulfill(status=200,content_type='application/json',body='{"available":false,"url":null}')
            elif url.startswith('http://bodymind.test/app-tesserato/'):
                req.fulfill(status=200,content_type='text/html; charset=utf-8',body=html)
            else:
                req.fulfill(status=200,content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300"/>')
        page.route('**/*',route)
        page.goto('http://bodymind.test/app-tesserato/'+token,wait_until='domcontentloaded')
        page.locator('.hero > .bm352-sky .bm352-cloud--far').wait_for()
        assert page.locator('.hero > .bm352-sky .bm352-dust').count()==2
        assert page.locator('main.main > .bm352-sky .bm352-cloud').count()==2
        sky=page.locator('.hero .bm352-cloud--near').first
        styles=sky.evaluate("""n=>{
          let s=getComputedStyle(n);
          return {animation:s.animationName,duration:s.animationDuration,opacity:s.opacity,filter:s.filter}
        }""")
        assert 'bm352-cloudfront' in styles['animation'],(width,styles)
        assert float(styles['opacity'])>=.35,(width,styles)
        assert 'blur(' in styles['filter']
        # The film has distinct, dark body, physical perforation rows and metal edging.
        fig=page.locator('#familyMediaTrack .media-card').first
        physical=fig.evaluate("""n=>{
          const b=getComputedStyle(n),holes=getComputedStyle(n,'::before'),post=getComputedStyle(n,'::after');
          return {background:b.backgroundImage,border:b.borderTopWidth,top:holes.content,
                  holes:holes.backgroundImage,height:holes.height,bottom:post.content}
        }""")
        assert 'gradient' in physical['background']
        assert int(float(physical['border'].replace('px','')))>=3
        assert physical['top']!='none' and physical['bottom']!='none'
        assert 'repeating-linear-gradient' in physical['holes']
        assert float(physical['height'].replace('px',''))>=20
        # Video center is never blurred but edges are alpha masked and unframed.
        video=page.locator('#familyHeroVideo')
        v=video.evaluate("""n=>{
          let s=getComputedStyle(n),wrap=getComputedStyle(n.parentElement);
          return {mask:s.maskImage||s.webkitMaskImage,filter:s.filter,
                  border:s.borderTopWidth,bg:s.backgroundColor,wrapBorder:wrap.borderTopWidth}
        }""")
        assert 'gradient' in v['mask'] and v['filter']=='none',(width,v)
        assert v['border']=='0px' and v['wrapBorder']=='0px',(width,v)
        nav=page.locator('nav.bottom-nav')
        handle=page.locator('body > .bm352-dock-handle')
        assert handle.count()==1
        assert page.locator('a.bm351-private-album').count()==1
        if width<=760:
            assert handle.is_visible()
            assert handle.get_attribute('aria-expanded')=='true'
            handle.click()
            assert nav.evaluate("(n)=>n.classList.contains('bm352-tucked')")
            assert handle.get_attribute('aria-expanded')=='false'
            assert not nav.locator('a').first.is_visible()
            handle.click()
            assert handle.get_attribute('aria-expanded')=='true'
            assert nav.locator('a').first.is_visible()
            page.evaluate("window.scrollTo(0,600)")
            page.wait_for_timeout(450)
            assert nav.evaluate("(n)=>n.classList.contains('bm352-tucked')"),width
            page.evaluate("window.scrollTo(0,150)")
            page.wait_for_timeout(450)
            assert not nav.evaluate("(n)=>n.classList.contains('bm352-tucked')"),width
        else:
            assert not handle.is_visible()
            assert nav.locator('a').first.is_visible()
        overflow=page.evaluate('document.documentElement.scrollWidth')
        assert overflow<=width+3,(width,overflow)
        assert not errors,(width,errors)
        print('A352_VISIBLE_FOG_TRUE_FILM_AND_SLIDE_DOCK_PASS',width,height)
        page.close()
    browser.close()
