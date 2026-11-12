"""Public-only read-only WebKit production smoke for BodyMind Stage 01.

No login, clicks that submit forms, or modification of content.
Outputs screenshots with public studio images only; it is a WebKit iPhone
viewport simulation, NOT a physical iPhone test.
"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
URL="https://bodymindaerialstudio.life/"
OUT=Path("evidence/stage01-live")
OUT.mkdir(parents=True,exist_ok=True)
async def inspect(browser,w,h,mobile):
 ctx=await browser.new_context(viewport={"width":w,"height":h},device_scale_factor=2,is_mobile=mobile,has_touch=mobile,locale="it-IT")
 page=await ctx.new_page()
 errors=[]
 page.on("pageerror",lambda e:errors.append(str(e)[:250]))
 response=await page.goto(URL,wait_until="domcontentloaded",timeout=65000)
 assert response and response.status==200,("Status",response.status if response else None)
 await page.locator('[data-bodymind-public="stage-01"]').wait_for(timeout=20000)
 await page.wait_for_function("() => document.querySelector('.bm-entrance-photo img')?.naturalWidth > 0 && document.querySelector('.site-logo img')?.naturalWidth > 0",timeout=28000)
 result=await page.evaluate("""() => {
 const box=sel=>{let e=document.querySelector(sel),r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};
 const logo=document.querySelector('.site-logo img'),hero=document.querySelector('.bm-entrance-photo img');
 return {viewport:innerWidth,scroll:document.documentElement.scrollWidth,
  hero:box('.bm-entrance'),photo:box('.bm-entrance-photo img'),title:box('.bm-entrance h1'),
  cta:box('.bm-entrance-cta'),logo:box('.site-logo'),wordmark:box('.bm-brand-wordmark'),menu:box('.site-header .menu-btn'),
  logoNatural:logo.naturalWidth,heroNatural:[hero.naturalWidth,hero.naturalHeight],
  heroSource:hero.getAttribute('src'),identitySource:document.querySelector('.bm-identity-photograph img')?.getAttribute('src'),
  medalMarquee:!!document.querySelector('.achievement-marquee'),
  familyLink:!!document.querySelector('a[href*="area-famiglie"]'),
  sections:['percorsi','kids','movimento','sedi','contatti'].map(id=>[id,!!document.getElementById(id)]),
  competition:!!document.querySelector('.competition-palmares'),
  greetingText:document.querySelector('.bm-entrance h1')?.textContent.trim()
 };
}""")
 print("BODYMIND_LIVE_IMAGE_DEBUG "+json.dumps({"viewport":f"{w}x{h}","actual":result["heroNatural"],"logo":result["logoNatural"],"stage":result["hero"]},ensure_ascii=False),flush=True)
 await page.screenshot(path=str(OUT/f"production-webkit-{w}x{h}.png"),animations="disabled")
 assert result["heroSource"]=="/seed-media/gallery5?v=9",("Wrong production hero URL",result["heroSource"])
 assert result["identitySource"]=="/seed-media/gallery1?v=9",("Wrong production identity URL",result["identitySource"])
 assert result["heroNatural"]==[764,1018],"Wrong real original BodyMind cover: "+str(result["heroNatural"])
 assert result["logoNatural"]>=200,"Brand mark absent"
 assert result["scroll"]<=w+2,"Horizontal page overflow"
 assert result["cta"]["w"]>=150 and result["cta"]["h"]>=44
 assert not result["medalMarquee"]
 assert all(flag for name,flag in result["sections"])
 assert result["competition"]
 if mobile:
  assert result["cta"]["y"]+result["cta"]["h"]<=h+3,"Trial booking hidden below the first viewport"
  print("BODYMIND_LIVE_HEADER_GEOMETRY "+json.dumps({"size":f"{w}x{h}","brand":result["wordmark"],"menu":result["menu"]}),flush=True)
  assert result["wordmark"]["w"]>65,"Brand wordmark unreadably narrow"
  assert result["wordmark"]["x"]+result["wordmark"]["w"]<=result["menu"]["x"]-4,"Brand mark actually overlaps menu"
  menu=page.locator('[data-menu]')
  await menu.click()
  assert await menu.get_attribute('aria-expanded')=='true',"Menu did not open"
  family=page.locator('[data-mobile-menu] a').filter(has_text="Area Famiglie")
  assert await family.count()==1,"Family link missing"
  await menu.click()
  assert await menu.get_attribute('aria-expanded')=='false',"Menu did not close"
 await page.screenshot(path=str(OUT/f"production-webkit-{w}x{h}.png"),animations="disabled")
 assert not errors,"JS errors "+repr(errors)
 await ctx.close()
 return result
async def main():
 results=[]
 async with async_playwright() as p:
  b=await p.webkit.launch()
  for w,h,m in ((390,844,True),(320,700,True),(430,932,True),(1440,900,False)):
   results.append({"size":f"{w}x{h}","result":await inspect(b,w,h,m)})
  await b.close()
 (OUT/"results.json").write_text(json.dumps(results,indent=2,ensure_ascii=False))
 print("BODYMIND_STAGE01_PUBLIC_LIVE_WEBKIT_PASS "+json.dumps([{"size":x["size"],"w":x["result"]["viewport"],"hero":x["result"]["heroNatural"]} for x in results]))
asyncio.run(main())
