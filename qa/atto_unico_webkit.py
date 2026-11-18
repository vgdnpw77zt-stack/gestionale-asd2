"""BodyMind ATTO UNICO: isolated Safari/WebKit functional AND visual smoke test.
Public website and management system are never modified; temporary local data only.
Safari WebKit viewport simulations, not real physical iPhones.
"""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright
URL="http://127.0.0.1:8765/"
OUT=Path("evidence/atto-unico")
OUT.mkdir(parents=True,exist_ok=True)
OUTCOME=[]

async def test_one(browser,w,h,mobile):
  ctx=await browser.new_context(viewport={"width":w,"height":h},
      is_mobile=mobile,has_touch=mobile,device_scale_factor=2,locale="it-IT")
  page=await ctx.new_page()
  errors=[]
  page.on("pageerror",lambda e:errors.append(str(e)[:250]))
  response=await page.goto(URL,wait_until="domcontentloaded",timeout=60000)
  assert response and response.status==200,("Site not reachable",w)
  await page.wait_for_function("() => document.querySelector('[data-hero-video]')?.videoWidth>0",timeout=30000)
  await page.wait_for_timeout(900)
  metrics=await page.evaluate("""() => {
    const rect=q=>{const e=document.querySelector(q);if(!e)return null;const r=e.getBoundingClientRect();
      return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height}};
    const vid=document.querySelector('[data-hero-video]');
    const strip=document.querySelector('.achievement-track');
    return {
      viewport:[innerWidth,innerHeight],pageWidth:document.documentElement.scrollWidth,
      header:rect('.site-header'),medals:rect('.achievement-marquee'),
      hero:rect('.hero-stage'),title:rect('.hero-copy h1'),
      cta:rect('.hero-actions .primary-btn'),video:rect('.hero-film video'),
      film:{muted:vid.muted,inline:vid.playsInline,w:vid.videoWidth,h:vid.videoHeight,paused:vid.paused,
        source:vid.querySelector('source')?.getAttribute('src'),poster:vid.getAttribute('poster')},
      animation:getComputedStyle(strip).animationName,
      family:[...document.querySelectorAll('a[href*="area-famiglie"]')].length,
      originalImgs:[...document.querySelectorAll('.act-image')].map(e=>e.getAttribute('src')),
      css:[...document.querySelectorAll('link[rel="stylesheet"]')].map(x=>x.href)
    };
  }""")
  assert metrics["pageWidth"]<=w+2,("Horizontal overflow",w,metrics["pageWidth"])
  assert metrics["medals"] and metrics["header"] and metrics["title"] and metrics["cta"]
  assert metrics["medals"]["top"]>=metrics["header"]["bottom"],("Medal strip hits logo",w,metrics)
  assert metrics["medals"]["bottom"]<metrics["title"]["top"],("Medal strip hits headline",w,metrics)
  assert metrics["video"]["width"]>=w*.7,("Original movie too narrow",w)
  assert metrics["film"]["muted"] and metrics["film"]["inline"]
  assert metrics["film"]["w"]==512 and metrics["film"]["h"]==768,("Video replaced",w,metrics["film"])
  assert metrics["film"]["poster"]=="/seed-media/gallery5?v=9"
  assert metrics["family"]>=2,("Area Famiglie navigation lost",w)
  assert len(metrics["originalImgs"])==3,("Original gallery count changed",w)
  assert all("/seed-media/gallery" in s for s in metrics["originalImgs"]),("Gallery replaced",w,metrics["originalImgs"])
  assert any("atto-unico.css" in s for s in metrics["css"])
  assert not any(("site.css" in s or "sunrise.css" in s) for s in metrics["css"]),("Old CSS stack still loading",w)
  assert await page.locator(".act").count()==3 and await page.locator("#training,#competition,#show").count()==3
  assert await page.locator(".acts-index a").count()==4
  assert await page.locator(".competition-palmares").count()==1
  assert await page.locator(".location-card").count()>=2
  assert await page.locator(".contact-links a").count()>=2
  if mobile:
    comp=await page.locator("#competition h3").evaluate("""e=>{
      const cs=getComputedStyle(e);return {text:e.textContent.trim(),scroll:e.scrollWidth,client:e.clientWidth,
      lineHeight:parseFloat(cs.lineHeight),height:e.getBoundingClientRect().height,whiteSpace:cs.whiteSpace}
    }""")
    assert comp["text"]=="COMPETITION",("Unexpected Competition copy",w)
    assert comp["scroll"]<=comp["client"]+2,("Competition heading cropped horizontally",w,comp)
    assert comp["height"]<=comp["lineHeight"]+3,("Competition heading wraps",w,comp)
  if mobile:
    assert metrics["title"]["top"]>=0 and metrics["title"]["bottom"]<h-1,("Hero title not in first screen",w,metrics)
    assert metrics["cta"]["top"]>=0 and metrics["cta"]["bottom"]<=h+2,("Booking CTA outside first screen",w,metrics)
  before=await page.locator("[data-hero-video]").evaluate("(e)=>e.currentTime")
  a=await page.locator(".achievement-track").evaluate("(e)=>getComputedStyle(e).transform")
  await page.wait_for_timeout(1200)
  after=await page.locator("[data-hero-video]").evaluate("(e)=>e.currentTime")
  b=await page.locator(".achievement-track").evaluate("(e)=>getComputedStyle(e).transform")
  assert after>before and not metrics["film"]["paused"],("Original film not autoplaying",w,before,after)
  assert metrics["animation"]=="bm-medals" and a!=b,("Achievements not moving",w)
  await page.screenshot(path=str(OUT/f"hero-{w}x{h}.png"),animations="disabled")
  if w in (390,1440):
    total=int(await page.evaluate("document.documentElement.scrollHeight"))
    for y in range(0,total,560):
      await page.evaluate("(n)=>window.scrollTo(0,n)",y)
      await page.wait_for_timeout(65)
    await page.wait_for_timeout(1200)
    await page.evaluate("window.scrollTo(0,0)")
    await page.wait_for_timeout(350)
    images=await page.locator(".act-image").evaluate_all("(es)=>es.map(e=>({ok:e.complete&&e.naturalWidth>0,src:e.currentSrc}))")
    assert len(images)==3 and all(x["ok"] for x in images),("Original photographs unavailable",w,images)
    await page.screenshot(path=str(OUT/f"home-completa-{w}x{h}.jpg"),
      full_page=True,type="jpeg",quality=82,animations="disabled")
    if w==390:
      for key,sel in [("training","#training"),("competition","#competition"),("show","#show"),("kids","#kids"),("metodo",".method"),("contatti","#contatti")]:
        await page.locator(sel).scroll_into_view_if_needed()
        await page.wait_for_timeout(150)
        await page.locator(sel).screenshot(path=str(OUT/f"section-{key}-390.png"),animations="disabled")
  await page.emulate_media(reduced_motion="reduce")
  assert await page.locator(".achievement-track").evaluate("(e)=>getComputedStyle(e).animationName")=="none"
  if mobile:
    menu=page.locator("[data-menu]")
    await menu.click()
    assert await menu.get_attribute("aria-expanded")=="true"
    await menu.click()
    assert await menu.get_attribute("aria-expanded")=="false"
  assert not errors,("JS console exception",w,errors)
  OUTCOME.append({"screen":f"{w}x{h}","result":"PASS","videoOriginal":True,
      "samePhotos":True,"medalsMoving":True,"headlineAndCtaVisible":True,
      "menuWorks":True,"noOverflow":True})
  await ctx.close()

async def main():
  async with async_playwright() as p:
    browser=await p.webkit.launch()
    for w,h,m in [(320,700,True),(390,844,True),(430,932,True),(1440,900,False)]:
      await test_one(browser,w,h,m)
    await browser.close()
  (OUT/"result.json").write_text(json.dumps(OUTCOME,indent=2,ensure_ascii=False))
  print("BODYMIND_ATTO_UNICO_WEBKIT_PASS "+json.dumps(OUTCOME,ensure_ascii=False))
asyncio.run(main())
