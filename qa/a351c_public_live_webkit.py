"""Read-only post-deployment QA: REAL public BodyMind A351c film, WebKit viewports.

Uses only GET and UI menu interactions. No owner/family accounts or data changes.
WebKit iPhone viewport emulation is not a physical iPhone.
"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright

URL="https://bodymindaerialstudio.life/"
OUT=Path("evidence/a351c-live")
OUT.mkdir(parents=True,exist_ok=True)
results=[]

async def verify(browser,w,h,mobile):
    context=await browser.new_context(viewport={"width":w,"height":h},
                                      is_mobile=mobile,has_touch=mobile,
                                      device_scale_factor=2,locale="it-IT")
    page=await context.new_page()
    js_errors=[]
    page.on("pageerror",lambda err:js_errors.append(str(err)[:120]))
    resp=await page.goto(URL,wait_until="domcontentloaded",timeout=55000)
    assert resp and resp.status==200,("Public HTTP",resp.status if resp else None)
    await page.locator("[data-hero-video]").wait_for(timeout=18000)
    await page.wait_for_function("() => !!document.querySelector('[data-hero-video]')?.videoWidth",timeout=18000)
    await page.wait_for_function("() => !!document.querySelector('.site-logo img')?.naturalWidth",timeout=18000)
    await page.wait_for_timeout(2300)
    state=await page.evaluate("""() => {
        const box=s=>{const el=document.querySelector(s),r=el.getBoundingClientRect(),style=getComputedStyle(el);
          return {y:Math.round(r.y),bottom:Math.round(r.bottom),w:Math.round(r.width),
                  size:parseFloat(style.fontSize),opacity:style.opacity}};
        const video=document.querySelector('[data-hero-video]');
        const dock=document.querySelector('.mobile-action-dock');
        return {
          viewport:[innerWidth,innerHeight],scroll:document.documentElement.scrollWidth,
          styles:[...document.querySelectorAll('link[rel=stylesheet]')].map(e=>e.href),
          heroTitle:box('.hero-fullscreen .hero-copy h1'),
          booking:box('.hero-fullscreen .primary-btn'),
          logoWidth:document.querySelector('.site-logo img').naturalWidth,
          video:{w:video.videoWidth,h:video.videoHeight,paused:video.paused,time:video.currentTime,muted:video.muted,inline:video.playsInline,src:video.querySelector('source')?.getAttribute('src')},
          poster:video.getAttribute('poster'),
          medalMarquee:!!document.querySelector('.achievement-marquee'),
          competition:!!document.querySelector('.competition-palmares'),
          kids:!!document.getElementById('kids'),
          contacts:!!document.getElementById('contatti'),
          family:!!document.querySelector('a[href*="area-famiglie"]'),
          dockHidden:dock?.classList.contains('is-on-stage'),
          extraProse:getComputedStyle(document.querySelector('.hero-fullscreen .hero-text')).display
        };
    }""")
    assert state["scroll"]<=w+2,("Horizontal overflow",w,state["scroll"])
    assert any("a351c-theatrical-video-20261112" in s for s in state["styles"]),("Old CSS on production",state["styles"])
    assert state["logoWidth"]>=100,("Original brand logo missing",w)
    assert state["video"]["muted"] and state["video"]["inline"],("iOS attributes lost",w)
    assert state["video"]["w"]==512 and state["video"]["h"]==768,("Unexpected source film",state["video"])
    assert state["poster"]=="/seed-media/gallery5?v=9",("Wrong poster",state["poster"])
    assert not state["medalMarquee"] and state["competition"]
    assert state["kids"] and state["contacts"] and state["family"]
    if mobile:
        assert 46<=state["heroTitle"]["size"]<=61
        assert state["booking"]["bottom"]<=h+3,("CTA below fold",w,state["booking"])
        assert state["dockHidden"],("Double booking CTA on opening screen",w)
        assert state["extraProse"]=="none",("Long description covers performer",w)
        if w==390:assert state["heroTitle"]["y"]>=410,("Heading over performer",state["heroTitle"])
    before=await page.locator('[data-hero-video]').evaluate('(v)=>v.currentTime')
    await page.wait_for_timeout(1200)
    after=await page.locator('[data-hero-video]').evaluate('(v)=>v.currentTime')
    assert after>before and not await page.locator('[data-hero-video]').evaluate('(v)=>v.paused'),("Film not playing",w,before,after)
    await page.screenshot(path=str(OUT/f"live-webkit-{w}x{h}.png"),animations="disabled")
    if mobile:
        menu=page.locator('[data-menu]')
        await menu.click()
        assert await menu.get_attribute('aria-expanded')=='true',("Menu failed",w)
        await page.locator('[data-mobile-menu] a[href="#percorsi"]').click()
        assert page.url.endswith('#percorsi'),("Link failed",w)
        await page.emulate_media(reduced_motion="reduce")
        await page.evaluate('scrollTo(0,0)')
        assert await page.locator('.hero-copy h1').is_visible()
    assert not js_errors,("JS errors",js_errors)
    results.append({"size":f"{w}x{h}","status":resp.status,
                    "title_size":state["heroTitle"]["size"],
                    "cta_bottom":state["booking"]["bottom"],
                    "film_decoded":[state["video"]["w"],state["video"]["h"]],
                    "autoplay":True,"logo_width":state["logoWidth"],
                    "ticker_removed":not state["medalMarquee"]})
    await context.close()

async def main():
    async with async_playwright() as p:
        browser=await p.webkit.launch()
        for w,h,m in [(320,700,True),(390,844,True),(430,932,True),(1440,900,False)]:
            await verify(browser,w,h,m)
        await browser.close()
    (OUT/"results.json").write_text(json.dumps(results,indent=2,ensure_ascii=False))
    print("BODYMIND_A351C_LIVE_WEBKIT_PASS "+json.dumps(results,ensure_ascii=False))

asyncio.run(main())
