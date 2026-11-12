"""Read-only QA of deployed BodyMind public site. NO data mutations or logins.

WebKit with iPhone viewport simulation; NOT an actual iPhone device.
The exact original production photos are loaded from the persisted site CMS
without replacing or rewriting them.
"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright

URL="https://bodymindaerialstudio.life/"
OUT=Path("evidence/a351d-live")
OUT.mkdir(parents=True,exist_ok=True)
REPORT=[]

async def main():
 async with async_playwright() as p:
  browser=await p.webkit.launch()
  for w,h,m in [(390,844,True),(320,700,True),(430,932,True),(1440,900,False)]:
   ctx=await browser.new_context(viewport={"width":w,"height":h},device_scale_factor=2,
                                  is_mobile=m,has_touch=m,locale="it-IT")
   page=await ctx.new_page()
   errors=[]
   page.on("pageerror",lambda exc:errors.append(str(exc)[:200]))
   resp=await page.goto(URL,wait_until="domcontentloaded",timeout=55000)
   assert resp and resp.status==200,("Production HTTP",w,resp.status if resp else None)
   await page.wait_for_function("() => document.querySelector('[data-hero-video]')?.videoWidth>0",timeout=25000)
   await page.wait_for_timeout(1100)
   before=await page.locator('[data-hero-video]').evaluate("(v)=>v.currentTime")
   await page.wait_for_timeout(950)
   after=await page.locator('[data-hero-video]').evaluate("(v)=>v.currentTime")
   v=await page.locator('[data-hero-video]').evaluate("(v)=>({w:v.videoWidth,h:v.videoHeight,muted:v.muted,inline:v.playsInline,paused:v.paused,src:v.querySelector('source')?.getAttribute('src')})")
   assert after>before and not v['paused'],("Original autoplay stopped",w,before,after,v)
   assert v['muted'] and v['inline'] and v['w']>0
   await page.screenshot(path=str(OUT/f"home-original-video-{w}.png"),animations="disabled")
   assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth+2"),("Horizontal overflow",w)
   css=await page.locator('link[rel="stylesheet"]').evaluate_all("(els)=>els.map(x=>x.href)")
   assert any("a351d-editorial-percorsi-20261112" in x for x in css),("Production does not serve A351d CSS",w,css)
   original_photos=[]
   for i,short in enumerate(["training","competition","show"],start=1):
    card=page.locator(f".program-card.p{i}")
    assert await card.count()==1,("Missing program",short)
    await card.scroll_into_view_if_needed()
    await page.wait_for_function(
      "(sel) => { const i=document.querySelector(sel+' .program-image img'); return !!i && i.complete && i.naturalWidth>0; }",
      arg=f".program-card.p{i}",timeout=26000)
    metadata=await card.evaluate("""(el) => {
      const picture=el.querySelector('.program-image'), img=picture.querySelector('img'), text=el.querySelector('.program-content');
      const a=picture.getBoundingClientRect(),b=text.getBoundingClientRect(),cs=getComputedStyle(img);
      return {src:img.getAttribute('src'),dimensions:[img.naturalWidth,img.naturalHeight],
          photoRect:{w:a.width,h:a.height,bottom:a.bottom},captionRect:{top:b.top},
          objectFit:cs.objectFit,copyPosition:getComputedStyle(text).position,
          title:el.querySelector('h3')?.textContent?.trim(),links:[...el.querySelectorAll('.program-links a')].map(x=>x.getAttribute('href'))}
    }""")
    assert metadata['dimensions'][0]>0 and metadata['dimensions'][1]>0,("Image not loaded",short,metadata)
    if m:
     assert metadata['objectFit']=="contain",("Image cropped",short,metadata)
     assert metadata['copyPosition']=="relative",("Caption overlaps athlete",short,metadata)
     assert metadata['captionRect']['top']>=metadata['photoRect']['bottom']-2,("Caption on top of photo",short,metadata)
     ratio=metadata['dimensions'][1]/metadata['dimensions'][0]
     assert abs(metadata['photoRect']['h']-metadata['photoRect']['w']*ratio)<5,("Photo has unnecessary empty bands",short,metadata)
    original_photos.append({"program":short,**metadata})
    if w==390:
     await card.screenshot(path=str(OUT/f"{short}-real-photo-390.png"),animations="disabled")
   assert await page.locator('.competition-palmares').count()==1,("Competition results missing",w)
   assert await page.locator('a[href*="area-famiglie"]').count()>=1,("Family access missing",w)
   assert await page.locator('#kids').count()==1
   assert await page.locator('#contatti').count()==1
   if m:
    dock_position=await page.locator('.mobile-action-dock').evaluate("(el)=>getComputedStyle(el).position")
    assert dock_position=="relative",("Quick actions obscure course photos",w,dock_position)
    menu=page.locator('[data-menu]')
    await menu.click()
    assert await menu.get_attribute('aria-expanded')=="true",("Menu did not open",w)
    await menu.click()
    assert await menu.get_attribute('aria-expanded')=="false",("Menu did not close",w)
   assert not errors,("JavaScript errors",w,errors)
   REPORT.append({"viewport":f"{w}x{h}","video_autoplay_advances":True,"video_metadata":v,
                  "photos":original_photos,"qa":"PASS"})
   await ctx.close()
  await browser.close()
 (OUT/"report.json").write_text(json.dumps(REPORT,indent=2,ensure_ascii=False))
 print("BODYMIND_A351D_PRODUCTION_WEBKIT_PASS "+json.dumps([{"viewport":x['viewport'],"photos":[p['src'] for p in x['photos']]} for x in REPORT],ensure_ascii=False))

asyncio.run(main())
