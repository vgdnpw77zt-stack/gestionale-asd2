"""BodyMind A351e — isolated original medal slider WebKit regression.
Read-only GET to public BodyMind site. No modifications to production.
The four device sizes are Safari WebKit viewport simulations, NOT physical iPhones.
"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright

URL="https://bodymindaerialstudio.life/"
OUT=Path("evidence/a351e-live")
OUT.mkdir(parents=True,exist_ok=True)
RESULTS=[]
METRICS="""() => {
 const box=(s)=>{const el=document.querySelector(s);if(!el)return null;const r=el.getBoundingClientRect();
   return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};
 const track=document.querySelector('.achievement-track');
 const v=document.querySelector('[data-hero-video]');
 const text=document.querySelector('.achievement-marquee');
 return {
  viewport:[innerWidth,innerHeight],scrollWidth:document.documentElement.scrollWidth,
  header:box('.site-header'),marquee:box('.hero-fullscreen .achievement-marquee'),
  title:box('.hero-fullscreen .hero-copy h1'),cta:box('.hero-actions .primary-btn'),
  window:box('.achievement-window'),film:box('.hero-film video'),
  visible:getComputedStyle(text).visibility,opacity:getComputedStyle(text).opacity,
  animation:getComputedStyle(track).animationName,transform:getComputedStyle(track).transform,
  medallists:[...text.querySelectorAll('.achievement-set')].map(e=>e.textContent.trim().replace(/\\s+/g,' ')),
  aria:text.getAttribute('aria-label'),copies:text.querySelectorAll('.achievement-set').length,
  secondHidden:text.querySelectorAll('.achievement-set')[1]?.getAttribute('aria-hidden')==='true',
  filmDetails:{muted:v.muted,inline:v.playsInline,paused:v.paused,w:v.videoWidth,h:v.videoHeight,
    source:v.querySelector('source')?.getAttribute('src'),poster:v.getAttribute('poster')},
  originalCourses:document.querySelectorAll('.program-card').length,
  competitionPalmares:!!document.querySelector('.competition-palmares'),
  family:!!document.querySelector('a[href*="area-famiglie"]'),
  css:[...document.querySelectorAll('link[rel=stylesheet]')].map(x=>x.href)
 };
}"""
async def check(browser,w,h,mobile):
 ctx=await browser.new_context(viewport={"width":w,"height":h},device_scale_factor=2,
                               is_mobile=mobile,has_touch=mobile,locale="it-IT")
 page=await ctx.new_page()
 errors=[]
 page.on("pageerror",lambda ex:errors.append(str(ex)[:160]))
 resp=await page.goto(URL,wait_until="domcontentloaded",timeout=50000)
 assert resp and resp.status==200,("Public BodyMind site not available",w)
 await page.wait_for_function("() => document.querySelector('[data-hero-video]')?.videoWidth>0",timeout=27000)
 await page.wait_for_timeout(1800)
 state=await page.evaluate(METRICS)
 assert state["scrollWidth"]<=w+2,("Horizontal scrolling",w,state["scrollWidth"])
 assert state["marquee"] and state["header"] and state["title"],("Missing strip/header/title",w)
 assert state["marquee"]["y"]>=state["header"]["bottom"]+1,("Medals hidden under sticky header",w,state)
 assert state["marquee"]["bottom"]<state["title"]["y"],("Medals cover heading and performer's lower composition",w,state)
 assert state["marquee"]["width"]>w*.75 and state["marquee"]["right"]<=w+1
 assert state["opacity"]=="1" and state["visible"]=="visible"
 assert state["copies"]==2 and state["secondHidden"]
 assert all(("4" in x and "3" in x and "10 podi" in x) for x in state["medallists"]),("Wrong real medal counts",w,state["medallists"])
 assert "4 medaglie d’oro, 3 d’argento e 3 di bronzo" in state["aria"]
 assert state["animation"]=="bodymind-achievement-scroll",("Original slide animation absent",w,state["animation"])
 assert state["originalCourses"]==3 and state["competitionPalmares"] and state["family"]
 assert state["filmDetails"]["muted"] and state["filmDetails"]["inline"]
 assert (state["filmDetails"]["w"],state["filmDetails"]["h"])==(512,768),("Original movie replaced",w,state["filmDetails"])
 assert state["filmDetails"]["poster"]=="/seed-media/gallery5?v=9"
 assert any("a351e-medal-slider-20261113" in x for x in state["css"])
 before=await page.locator('[data-hero-video]').evaluate("(v)=>v.currentTime")
 offset=await page.locator('.achievement-track').evaluate("(e)=>getComputedStyle(e).transform")
 await page.wait_for_timeout(1100)
 after=await page.locator('[data-hero-video]').evaluate("(v)=>v.currentTime")
 offset_after=await page.locator('.achievement-track').evaluate("(e)=>getComputedStyle(e).transform")
 assert after>before and not await page.locator('[data-hero-video]').evaluate("(v)=>v.paused"),("Autoplay frozen",w,before,after)
 assert offset!=offset_after,("Medal strip doesn't move",w)
 await page.screenshot(path=str(OUT/f"hero-medals-original-film-{w}x{h}.png"),animations="disabled")
 await page.emulate_media(reduced_motion="reduce")
 assert await page.locator('.achievement-track').evaluate("(e)=>getComputedStyle(e).animationName")=="none",("Reduced motion ignored",w)
 assert await page.locator('.achievement-marquee').is_visible()
 if mobile:
  menu=page.locator('[data-menu]')
  await menu.click()
  assert await menu.get_attribute("aria-expanded")=="true",("Menu blocked",w)
  await menu.click()
  assert await menu.get_attribute("aria-expanded")=="false"
 assert not errors,("JS error",errors)
 RESULTS.append({"viewport":f"{w}x{h}","medalRibbonBelowHeader":True,
                 "videoOriginalPlaying":True,"medalMovement":True,"reducedMotion":True,
                 "titleUnobscured":True,"noHorizontalScroll":True})
 await ctx.close()

async def main():
 async with async_playwright() as p:
  browser=await p.webkit.launch()
  for w,h,m in [(320,700,True),(390,844,True),(430,932,True),(1440,900,False)]:
   await check(browser,w,h,m)
  await browser.close()
 (OUT/"report.json").write_text(json.dumps(RESULTS,indent=2,ensure_ascii=False))
 print("BODYMIND_A351E_LIVE_MEDALS_WEBKIT_PASS "+json.dumps(RESULTS,ensure_ascii=False))

asyncio.run(main())
