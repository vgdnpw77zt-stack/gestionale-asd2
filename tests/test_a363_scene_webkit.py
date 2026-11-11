#!/usr/bin/env python3
"""Safe A363b WebKit style/interaction contract on a synthetic structure.

This is deliberately NOT evidence of authenticated visual production QA.
A real-family WebKit session and screenshots are required separately.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE=Path('bootstrap/family_a362_base.css').read_text()
SCENE=Path('bootstrap/family_a362_scene.css').read_text()
RUNTIME=Path('bootstrap/family_a362_runtime.py').read_text()
assert 'data-bodymind-scene="A363b"' in RUNTIME
assert "X-BodyMind-Family-Release']='A363b'" in RUNTIME
assert "SOURCE_SHA='35afdadb806a9ad1f22188e7f20439356f7282dad3adb4fc867554485ee4f686'" in RUNTIME
assert 'bm362-sky--main' in RUNTIME and 'bm362-sky--main' in SCENE
assert '#ffc0d2' in SCENE and '#72ffe1' in SCENE
assert 'bm363-luminous' in SCENE and 'bm362-wave' in SCENE
assert 'hero-media .family-hero-video' in SCENE
assert "bm360-cinematic" not in SCENE
assert "family_a360" not in RUNTIME

# Test geometry with the same class names as original A362 without claiming
# that an invented HTML fragment is the authenticated Home.
HTML="""<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>"""+BASE+SCENE+"""</style></head><body>
<section class="hero" id="top">
 <div class="bm362-sky"><div class="bm362-cloud"></div><div class="bm362-cloud bm362-cloud--near"></div><div class="bm362-stars"></div>
 <svg class="bm362-waves" viewBox="0 0 800 400"><path d="M0 0Q90 40 800 300"></path></svg></div>
 <div class="hero-media"><video class="family-hero-video" muted playsinline></video></div>
 <div class="frame hero-content"><div class="hero-intro"><span class="eyebrow">BODYMIND</span>
 <h1>Ciao, atleta</h1><p>Il tuo percorso</p><a class="pill" href="#corsi">Corsi</a><button id="familyHeroPlayback" class="hero-playback">Pausa</button></div></div>
</section>
<main class="frame main">
 <div class="bm362-sky bm362-sky--main"><div class="bm362-cloud"></div><div class="bm362-stars"></div></div>
 <div class="stats"><a class="stat" href="#corsi">Scheda corso</a><a class="stat" href="#pagamenti">Pagamenti</a></div>
 <section id="corsi" class="section"><h2>Corsi</h2></section><section id="pagamenti" class="section"><h2>Pagamenti</h2></section>
 <section id="media" class="section"><div class="media-track"><div class="media-card">Foto</div></div></section>
 </main><nav class="bottom-nav"><a href="#corsi">Corsi</a><a href="#pagamenti">Pagamenti</a></nav>
 </body></html>"""
JS="""() => {
 const x=s=>{const e=document.querySelector(s),b=e.getBoundingClientRect(),c=getComputedStyle(e);
 return {x:b.x,y:b.y,w:b.width,h:b.height,pos:c.position,filter:c.filter,z:c.zIndex,mask:c.webkitMaskImage||c.maskImage,display:c.display,
 animation:c.animationName}};
 return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 hero:x('.hero'),media:x('.hero-media'),intro:x('.hero-content'),
 video:x('.hero video'),hello:x('.hero h1'),cloud:x('.bm362-cloud'),
 waves:x('.bm362-waves'),mainSky:x('.main>.bm362-sky--main'),
 waveStroke:parseFloat(getComputedStyle(document.querySelector('.bm362-waves path')).strokeWidth),
 stardustOpacity:parseFloat(getComputedStyle(document.querySelector('.bm362-stars')).opacity),
 cloudLayers:getComputedStyle(document.querySelector('.bm362-cloud')).backgroundImage.split('radial-gradient(').length-1};
}"""

async def run():
 async with async_playwright() as p:
  browser=await p.webkit.launch()
  for width,height in [(320,640),(390,664),(390,844),(430,932),(768,900),(1440,900)]:
   page=await browser.new_page(viewport={'width':width,'height':height},device_scale_factor=2,is_mobile=width<500,has_touch=width<500)
   await page.set_content(HTML,wait_until='load')
   state=await page.evaluate(JS)
   assert state['scrollWidth']<=width+2,(width,'overflow',state['scrollWidth'])
   assert state['video']['filter']=='none',(width,state['video'])
   assert state['cloud']['animation']=='bm362-cloud-a',(width,state['cloud'])
   assert state['waves']['animation']=='bm362-wave',(width,state['waves'])
   assert state['waveStroke']>=2.4,(width,'Waves are too faint',state['waveStroke'])
   assert state['stardustOpacity']>=0.90,(width,'Stardust opacity',state['stardustOpacity'])
   assert state['cloudLayers']>=4,(width,'Missing dense cloud layers',state['cloudLayers'])
   if width<=760:
    assert state['media']['pos']=='absolute',(width,state['media'])
    assert state['intro']['pos']=='absolute',(width,state['intro'])
    assert state['hero']['h']>=700,(width,state['hero'])
    assert state['media']['mask'] not in ('none',''),(width,state['media'])
    assert state['mainSky']['display']!='none',(width,state['mainSky'])
   else:
    assert state['hero']['h']>=700,(width,state['hero'])
   before=await page.locator('.bm362-cloud').first.evaluate('(e)=>getComputedStyle(e).transform')
   await page.wait_for_timeout(700)
   after=await page.locator('.bm362-cloud').first.evaluate('(e)=>getComputedStyle(e).transform')
   assert before!=after,(width,'clouds static')
   await page.locator('a.pill').click()
   assert page.url.endswith('#corsi'),(width,'Corsi link failed')
   print('A363b SYNTHETIC WEBKIT GEOMETRY PASS',width,height)
   await page.close()
  await browser.close()
asyncio.run(run())
