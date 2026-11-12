"""A351d editorial paths public-site preview: WebKit device simulation, not iPhone hardware.
Read only public studio media. No production deploy, no database or CRM writes."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
BASE="http://127.0.0.1:8765/"
OUT=Path("evidence/a351d");OUT.mkdir(parents=True,exist_ok=True)
REPORT=[]
JS="""() => {
 const box=s=>{let el=document.querySelector(s),r=el.getBoundingClientRect(),cs=getComputedStyle(el);
 return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
 bottom:Math.round(r.bottom),top:Math.round(r.top),position:cs.position,display:cs.display,
 color:cs.color,bg:cs.backgroundColor,radius:cs.borderRadius,fit:cs.objectFit}};
 const cards=[...document.querySelectorAll('.program-card')].map((card,i)=>{
    const photo=card.querySelector('.program-image'),img=photo.querySelector('img'),copy=card.querySelector('.program-content'),links=card.querySelectorAll('.program-links a');
    const x=(e)=>{let r=e.getBoundingClientRect();return {top:Math.round(r.top),bottom:Math.round(r.bottom),width:Math.round(r.width),height:Math.round(r.height)}};
    return {name:card.querySelector('h3')?.textContent?.trim(),card:x(card),photo:x(photo),
      text:x(copy),img:[img.naturalWidth,img.naturalHeight],links:[...links].map(e=>e.getAttribute('href')),
      overlay:getComputedStyle(card.querySelector('.program-overlay')).display,
      imageFit:getComputedStyle(img).objectFit,cardRadius:getComputedStyle(card).borderRadius,
      copyPosition:getComputedStyle(copy).position,hasPalmares:!!card.querySelector('.competition-palmares')}
 });
 const v=document.querySelector('[data-hero-video]');
 return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
  cards,video:{src:v?.querySelector('source')?.getAttribute('src'),width:v?.videoWidth,height:v?.videoHeight,
              time:v?.currentTime,paused:v?.paused,muted:v?.muted,inline:v?.playsInline},
  heroTitle:box('.hero-copy h1'),firstCTA:box('.hero-actions .primary-btn'),
  family:!!document.querySelector('a[href*="area-famiglie"]'),hasKids:!!document.querySelector('#kids'),
  hasShow:!!document.querySelector('.program-card.p3'),css:[...document.querySelectorAll('link[rel=stylesheet]')].map(x=>x.href)};
}"""
async def check(browser,w,h):
 mobile=w<=600
 ctx=await browser.new_context(viewport={"width":w,"height":h},is_mobile=mobile,
                               has_touch=mobile,device_scale_factor=2,locale="it-IT")
 page=await ctx.new_page()
 errors=[]
 page.on("pageerror",lambda e:errors.append(str(e)))
 resp=await page.goto(BASE,wait_until="domcontentloaded",timeout=45000)
 assert resp and resp.status==200
 await page.wait_for_function("() => document.querySelector('[data-hero-video]')?.videoWidth > 0",timeout=26000)
 await page.wait_for_timeout(1300)
 # These original course photographs are intentionally loading=lazy.
 # Scroll to each card, triggering the browser's real network fetch.
 for selector in [".program-card.p1", ".program-card.p2", ".program-card.p3"]:
  await page.locator(selector).scroll_into_view_if_needed()
  await page.wait_for_function(
   "(sel) => { const img=document.querySelector(sel+' .program-image img'); return !!img && img.complete && img.naturalWidth>0; }",
   arg=selector,timeout=22000)
 state=await page.evaluate(JS)
 assert state["scrollWidth"]<=w+2,("horizontal overflow",w,state["scrollWidth"])
 assert len(state["cards"])==3
 assert state["cards"][0]["name"]=="TRAINING"
 assert state["cards"][1]["name"]=="COMPETITION"
 assert state["cards"][2]["name"]=="SHOW"
 assert state["video"]["src"]=="/static/media/bodymind-performing-hero.mp4"
 assert state["video"]["width"]==512 and state["video"]["height"]==768
 assert state["video"]["inline"] and state["video"]["muted"] and not state["video"]["paused"]
 assert state["family"] and state["hasKids"] and state["hasShow"]
 assert any("a351d-editorial-percorsi-20261112" in s for s in state["css"])
 before=await page.locator('[data-hero-video]').evaluate("(v)=>v.currentTime")
 await page.wait_for_timeout(950)
 after=await page.locator('[data-hero-video]').evaluate("(v)=>v.currentTime")
 assert after>before,("Hero playback did not advance",before,after)
 if mobile:
  for i,card in enumerate(state["cards"]):
   assert card["img"][0]>=600 and card["img"][1]>=600,("Course image is low-quality or missing",card)
   assert card["overlay"]=="none",("Unnecessary photo overlay",card)
   assert card["copyPosition"]=="relative",("Caption still covers the performer",card)
   assert card["text"]["top"]>=card["photo"]["bottom"]-2,("Text overlaps photo",card)
   assert card["imageFit"]=="contain",("Photo is being cropped",card)
   assert card["cardRadius"] in ["12px","12px 12px 12px 12px"],("Old rounded tile still active",card)
   assert card["links"],("Lost navigation",card)
  assert state["cards"][1]["hasPalmares"]
  await page.locator(".program-card.p1").scroll_into_view_if_needed()
  await page.wait_for_timeout(600)
  await page.locator(".program-card.p1").screenshot(path=str(OUT/f"training-{w}.png"),animations="disabled")
  if w==390:
   for sel,name in [(".program-card.p2","competition"),(".program-card.p3","show")]:
    await page.locator(sel).scroll_into_view_if_needed()
    await page.wait_for_timeout(500)
    await page.locator(sel).screenshot(path=str(OUT/f"{name}-{w}.png"),animations="disabled")
   await page.evaluate("scrollTo(0,0)")
   await page.screenshot(path=str(OUT/"hero-preserved-390.png"),animations="disabled")
  menu=page.locator('[data-menu]');await menu.click()
  assert await menu.get_attribute("aria-expanded")=="true"
  await menu.click()
  assert await menu.get_attribute("aria-expanded")=="false"
  await page.emulate_media(reduced_motion="reduce")
  assert await page.locator('.program-card.p1').is_visible() or await page.locator('.program-card.p1').count()==1
 assert not errors,("JS errors",errors)
 REPORT.append({"width":w,"height":h,"heroPlaying":True,
   "programs":[{"name":c["name"],"image":c["img"],"photographic":c["imageFit"]} for c in state["cards"]],
   "noHorizontalOverflow":True,"preservesFamily":state["family"]})
 await ctx.close()
async def main():
 async with async_playwright() as p:
  browser=await p.webkit.launch()
  for w,h in [(320,700),(390,844),(430,932),(1440,900)]:
   await check(browser,w,h)
  await browser.close()
 (OUT/"report.json").write_text(json.dumps(REPORT,indent=2,ensure_ascii=False))
 print("BODYMIND_A351D_EDITORIAL_WEBKIT_PASS "+json.dumps(REPORT,ensure_ascii=False))
asyncio.run(main())
