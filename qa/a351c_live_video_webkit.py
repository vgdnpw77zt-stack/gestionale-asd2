"""A351c read-only production baseline vs ISOLATED preview in WebKit.

Only public Home; never logs into Area Famiglie; no POST requests to production.
WebKit device presets simulate iPhone viewports; not a physical iPhone test.
"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path("evidence/a351c")
ROOT.mkdir(parents=True,exist_ok=True)
LIVE="https://bodymindaerialstudio.life/"
PREVIEW="http://127.0.0.1:8765/"
REPORT=[]

JS="""() => {
const box=(q)=>{let el=document.querySelector(q);if(!el)return null;
const b=el.getBoundingClientRect(),c=getComputedStyle(el);
return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
 bottom:Math.round(b.bottom),fontSize:c.fontSize,position:c.position,visibility:c.visibility,
 opacity:c.opacity,color:c.color,background:c.backgroundImage};};
const v=document.querySelector('[data-hero-video]'),logo=document.querySelector('.site-logo img'),dock=document.querySelector('.mobile-action-dock');
return {viewport:[innerWidth,innerHeight],scrollWidth:document.documentElement.scrollWidth,
  hero:box('.hero-stage.hero-fullscreen'),title:box('.hero-fullscreen .hero-copy h1'),
  copy:box('.hero-fullscreen .hero-copy'),signature:box('.hero-signature'),
  video:box('.hero-film video'),poster:v?.getAttribute('poster'),
  src:v?.querySelector('source')?.getAttribute('src'),controlsPlay:!!document.querySelector('[data-native-play]'),
  videoState:{width:v?.videoWidth??0,height:v?.videoHeight??0,paused:v?.paused??true,
              ready:v?.readyState??0,time:v?.currentTime??0,muted:v?.muted,playsinline:v?.playsInline},
  ticker:!!document.querySelector('.achievement-marquee'),
  logoNatural:logo?.naturalWidth??0,dockHidden:dock?.classList.contains('is-on-stage')??false,
  heroProseDisplay:getComputedStyle(document.querySelector('.hero-fullscreen .hero-text')).display,
  competitor:!!document.querySelector('.competition-palmares'),
  kids:!!document.getElementById('kids'),
  booking:box('.hero-fullscreen .primary-btn'),
  menu:box('[data-menu]'),
  intro:box('.editorial-intro'),
  family:!!document.querySelector('a[href*="area-famiglie"]'),
  look:{body:getComputedStyle(document.body).backgroundColor,
        stage:getComputedStyle(document.querySelector('.hero-stage')).backgroundImage.slice(0,450),
        btn:getComputedStyle(document.querySelector('.hero-actions .primary-btn')).backgroundImage.slice(0,200)}
};}"""

async def check(browser,width,height,mobile):
    ctx=await browser.new_context(viewport={"width":width,"height":height},device_scale_factor=2,
                                  is_mobile=mobile,has_touch=mobile,locale="it-IT")
    page=await ctx.new_page()
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)[:220]))
    r=await page.goto(PREVIEW,wait_until="domcontentloaded",timeout=50000)
    assert r and r.status==200,("Preview HTTP status",r.status if r else None)
    await page.locator(".hero-film video").wait_for(timeout=16000)
    await page.evaluate("document.fonts.ready")
    await page.wait_for_timeout(3200)
    state=await page.evaluate(JS)
    assert state["scrollWidth"]<=width+2,("Horizontal overflow",width,state["scrollWidth"])
    assert state["title"]["w"]>170 and state["title"]["opacity"]=="1",("Title invisible",state["title"])
    assert state["booking"] and state["booking"]["w"]>=150 and state["booking"]["h"]>=44
    assert state["videoState"]["muted"] and state["videoState"]["playsinline"]
    assert state["src"] and "mp4" in state["src"]
    assert state["video"]["w"]>=width-3 if mobile else state["video"]["w"]>500
    assert state["videoState"]["width"]>0 and state["videoState"]["height"]>0,("Video not decoded in WebKit",state["videoState"])
    assert state["controlsPlay"],"Native fallback button must be preserved"
    assert state["logoNatural"]>0,("Original BodyMind logo unavailable, including public fallback",state["logoNatural"])
    assert not state["ticker"],"Top medal strip still blocks theatrical scene"
    assert state["competitor"] and state["kids"] and state["family"]
    assert "0a1018" in state["look"]["body"].lower() or "10, 16, 24" in state["look"]["body"],("Wrong new stage background",state["look"]["body"])
    if mobile:
        assert state["heroProseDisplay"]=="none",("Duplicate long copy still covers performer",width)
        assert state["dockHidden"],("Duplicate booking dock overlays film",width)
        assert state["title"]["fontSize"].endswith("px")
        fontsize=float(state["title"]["fontSize"][:-2])
        assert 46<=fontsize<=61,("Heading outside legible iPhone range",fontsize)
        assert state["booking"]["y"]+state["booking"]["h"]<=height+3,("CTA off first viewport",state["booking"])
        if width==390:
            assert state["title"]["y"]>=410,("Dancer face still covered by headline",state["title"])
        assert state["hero"]["h"]>=height-10,("Hero too short",state["hero"])
    before=await page.locator("[data-hero-video]").evaluate("(e)=>e.currentTime")
    await page.wait_for_timeout(1300)
    after=await page.locator("[data-hero-video]").evaluate("(e)=>e.currentTime")
    moving=after>before and not await page.locator("[data-hero-video]").evaluate("(e)=>e.paused")
    state["videoPlaybackAdvanced"]=moving
    # Browser codec support can differ from iOS hardware; never fake autoplay
    # confirmation. Require actual advancing clock in simulated WebKit.
    assert moving,("Autoplay did not advance in WebKit",before,after,state["videoState"])
    assert not errors,("JavaScript errors",errors)
    await page.evaluate("scrollTo(0,0)")
    await page.screenshot(path=str(ROOT/f"new-webkit-{width}x{height}.png"),animations="disabled")
    if width==390:
        await page.locator('.editorial-intro').scroll_into_view_if_needed()
        await page.locator('.editorial-intro .intro-left.reveal.in').wait_for(timeout=7000)
        await page.screenshot(path=str(ROOT/"new-identity-390.png"),animations="disabled")
    if mobile:
        menu=page.locator('[data-menu]')
        await menu.click()
        assert await menu.get_attribute("aria-expanded")=="true",("Mobile menu failed",width)
        await page.locator('[data-mobile-menu] a[href="#percorsi"]').click()
        assert page.url.endswith("#percorsi"),("Menu anchor failed",width)
        await page.emulate_media(reduced_motion="reduce")
        await page.evaluate("scrollTo(0,0)")
        assert await page.locator('.hero-copy h1').is_visible(),("Reduce-motion title missing",width)
    state["width"]=width
    REPORT.append({k:state[k] for k in ("width","viewport","title","booking","poster","src","ticker","competitor","videoState","videoPlaybackAdvanced")})
    await ctx.close()

async def baseline(browser):
    ctx=await browser.new_context(viewport={"width":390,"height":844},device_scale_factor=2,is_mobile=True,has_touch=True)
    page=await ctx.new_page()
    try:
        response=await page.goto(LIVE,wait_until="domcontentloaded",timeout=55000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(ROOT/"previous-live-webkit-390.png"),animations="disabled")
        print("BODYMIND_A351C_PUBLIC_BASELINE "+json.dumps({"status":response.status if response else None}))
    finally:
        await ctx.close()

async def main():
    async with async_playwright() as p:
        browser=await p.webkit.launch()
        await baseline(browser)
        for w,h,m in [(320,700,True),(390,844,True),(430,932,True),(1440,900,False)]:
            await check(browser,w,h,m)
        await browser.close()
    (ROOT/"metrics.json").write_text(json.dumps(REPORT,indent=2,ensure_ascii=False))
    print("BODYMIND_A351C_ORIGINAL_VIDEO_WEBKIT_PASS "+json.dumps(REPORT,ensure_ascii=False))

asyncio.run(main())
