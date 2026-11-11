#!/usr/bin/env python3
"""Read-only, privacy-preserving authenticated WebKit iPhone QA of REAL BodyMind.

No Flask routes, form submissions, token logging, or telemetry. The only
screenshot is of the hero, with the personal greeting replaced in memory
just during capture; screenshots are encrypted before leaving the runner.
"""
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

PHASE=os.environ.get("A363_PHASE","before")
assert PHASE in ("before","after")
ROOT=Path("evidence")
ROOT.mkdir(exist_ok=True)

JS_STATE="""() => {
  const one=(s)=>{
    const e=document.querySelector(s);if(!e)return {found:false};
    const r=e.getBoundingClientRect(), c=getComputedStyle(e);
    return {found:true, x:Math.round(r.x),y:Math.round(r.y),
      width:Math.round(r.width),height:Math.round(r.height),
      position:c.position,display:c.display,overflow:c.overflow,
      z:c.zIndex,filter:c.filter,mask:c.webkitMaskImage||c.maskImage,
      animation:c.animationName,background:c.backgroundImage.slice(0,300)};
  };
  const v=document.querySelector('.hero video');
  const c=document.querySelector('.bm362-cloud');
  return {
    viewport:{width:innerWidth,height:innerHeight,
      scrollWidth:document.documentElement.scrollWidth},
    familyRelease:document.body.getAttribute('data-bodymind-family'),
    stylesheetLinks:document.querySelectorAll('link[rel="stylesheet"]').length,
    styles:document.querySelectorAll('style').length,
    hero:one('.hero'),media:one('.hero-media'),
    heroContent:one('.hero .hero-content'),
    intro:one('.hero .hero-intro'),
    hello:one('.hero h1'),videoBox:one('.hero video'),
    sky:one('.hero>.bm362-sky'),cloud:one('.bm362-cloud'),
    nearCloud:one('.bm362-cloud--near'),
    waves:one('.bm362-waves'),main:one('main.main'),
    hasNav:!!document.querySelector('.bottom-nav'),
    hasGallery:!!document.querySelector('.media-track'),
    hasStudio:!!document.querySelector('.bm362-studio a'),
    hasPrivateAlbum:!!document.querySelector('.bm351-private-album'),
    hasDocuments:!!document.getElementById('documenti'),
    hasCourses:!!document.getElementById('corsi'),
    hasPayments:!!document.getElementById('pagamenti'),
    hasReceipts:!!document.querySelector('.receipts a'),
    hasUploads:!!document.querySelector('.upload input[name="csrf_token"]'),
    video:{
      found:!!v,muted:!!v?.muted,autoplay:!!v?.autoplay,playsinline:!!v?.playsInline,
      paused:!!v?.paused,ready:v?.readyState??0,w:v?.videoWidth??0,
      h:v?.videoHeight??0,time:Math.round((v?.currentTime||0)*10)/10},
    cloudTransform:c?getComputedStyle(c).transform:null
  };
}"""

async def main():
    token=Path('/tmp/bm-family-token').read_text().strip()
    assert token and len(token)<200
    url="https://app.bodymindaerialstudio.life/app-tesserato/"+token
    async with async_playwright() as p:
        browser=await p.webkit.launch()
        page=await browser.new_page(**p.devices["iPhone 13"])
        errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)[:150]))
        response=await page.goto(url,wait_until='domcontentloaded',timeout=60000)
        assert response and response.status==200, "Authenticated family response not HTTP 200"
        assert response.headers.get("x-bodymind-family-release")==("A362" if PHASE=="before" else "A363"),"Wrong live family release"
        await page.locator('.hero h1').wait_for(timeout=20000)
        await page.locator('.hero video').wait_for(timeout=15000)
        await page.wait_for_timeout(2000)
        s=await page.evaluate(JS_STATE)
        assert s['hero']['width']>300 and s['video']['w']>0 and s['video']['h']>0, "Real hero film did not load"
        assert s["video"]["muted"] and s["video"]["playsinline"], "iOS video attributes lost"
        before_time=await page.locator(".hero video").evaluate('(e)=>e.currentTime')
        before_cloud=await page.locator(".bm362-cloud").first.evaluate('(e)=>getComputedStyle(e).transform')
        await page.wait_for_timeout(1900)
        after_time=await page.locator(".hero video").evaluate('(e)=>e.currentTime')
        after_cloud=await page.locator(".bm362-cloud").first.evaluate('(e)=>getComputedStyle(e).transform')
        s['motion']={'videoAdvances':after_time>before_time,
                     'cloudMoves':after_cloud!=before_cloud}
        assert s['motion']['videoAdvances'] and not s['video']['paused'], "Autoplay did not actually run"
        assert s['motion']['cloudMoves'], "Cloud layer is static"
        assert s['viewport']['scrollWidth']<=s['viewport']['width']+2,"Horizontal overflow on iPhone"
        if PHASE=="after":
            assert s['videoBox']['filter']=="none","Video blur/filter present"
            assert s['intro']['position']=='absolute',"Greeting is not integrated in hero"
            assert s['media']['position']=='absolute',"Film is not in integrated hero"
            assert s['sky']['found'] and s['waves']['found'],"Nebula or waves missing"
            assert s['media']['mask'] not in ('none',''),"Video side feather not in computed CSS"
            assert s['hero']['height']>=640,"Hero too short for native film and greeting"
            # Hello cannot cover the central performance zone (center third of the film).
            h=s['hello'];v=s['videoBox']
            collision=(h['x']<v['x']+v['width']*0.66 and
                h['x']+h['width']>v['x']+v['width']*0.33 and
                h['y']<v['y']+v['height']*0.71 and
                h['y']+h['height']>v['y']+v['height']*0.22)
            assert not collision,"Greeting covers central film subject"
        # Read-only interaction checks: no forms submitted, no uploads, no account changes.
        pause=page.locator('#familyHeroPlayback')
        assert await pause.count()==1
        await pause.click()
        assert await page.locator('.hero video').evaluate('(e)=>e.paused'),"Pause control broken"
        await pause.click()
        await page.wait_for_timeout(500)
        assert not await page.locator('.hero video').evaluate('(e)=>e.paused'),"Play control broken"
        toggle=page.locator('.bm362-menu')
        assert await toggle.count()==1
        await toggle.click()
        assert await toggle.get_attribute('aria-expanded')=='true',"Navigation did not open"
        await page.locator('.bottom-nav a[href="#documenti"]').click()
        assert await page.locator('#documenti').count()==1
        assert await toggle.get_attribute('aria-expanded')=='false',"Navigation did not close"
        for target in ('corsi','pagamenti','media','top'):
            await toggle.click()
            await page.locator('.bottom-nav a[href="#'+target+'"]').click()
            assert page.url.split('#')[-1]==target,"Broken anchor: "+target
        assert s['hasGallery'] and s['hasStudio'] and s['hasPrivateAlbum'],"Gallery / studio / album missing"
        assert s['hasReceipts'] and s['hasUploads'],"Receipts or upload CSRF lost"
        assert not errors, "JavaScript error on private Home"
        # Screenshot only authentic hero composition, no other family panels.
        # The greeting is anonymized IN THE BROWSER just during screenshot.
        await page.locator('#top').scroll_into_view_if_needed()
        await page.locator('.hero h1').evaluate("(e)=>{e.textContent='Ciao, atleta';}")
        await page.locator('.hero').screenshot(path=str(ROOT/('webkit-'+PHASE+'-hero.png')),
                                            timeout=25000,animations="allow")
        # No identifying details, cookies, private URLs, names, or media HTML in JSON.
        (ROOT/('state-'+PHASE+'.json')).write_text(json.dumps(s,indent=2,ensure_ascii=False))
        print("BODYMIND_A363_WEBKIT_"+PHASE.upper()+"_PASS "+
              json.dumps({"status":response.status,"release":response.headers.get("x-bodymind-family-release"),
                          "viewport":s['viewport'],"videoSize":[s['video']['w'],s['video']['h']],
                          "videoAdvances":s['motion']['videoAdvances'],
                          "cloudMoves":s['motion']['cloudMoves'],
                          "heroHeight":s['hero']['height'],
                          "helloPosition":s['intro']['position'],
                          "links":{k:s[k] for k in ('hasGallery','hasStudio','hasPrivateAlbum',
                                        'hasDocuments','hasCourses','hasPayments','hasReceipts','hasUploads')}}))
        await browser.close()

asyncio.run(main())
