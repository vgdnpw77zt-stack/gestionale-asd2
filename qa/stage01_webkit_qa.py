"""Stage 01: public-only, non-destructive layout and authentic media QA.

This is WebKit desktop/iPhone viewport simulation, NOT an actual iPhone device.
Live baseline screenshots are attempted separately from local branch screenshots.
Production data and media are never edited.
"""
import asyncio
import json
import os
from pathlib import Path
from urllib.request import urlopen,Request
from io import BytesIO
from PIL import Image
from playwright.async_api import async_playwright

OUT=Path("evidence/stage01")
OUT.mkdir(parents=True,exist_ok=True)
LOCAL="http://127.0.0.1:8765/"
LIVE="https://bodymindaerialstudio.life/"
REPORT={"stage":"01","environment":"CI simulated WebKit","screens":[],"live_baseline":None}

def media_probe():
    found=[]
    for name,url in [
        ("original-hero","https://bodymindaerialstudio.life/static/media/bodymind-hero.webp"),
        ("gallery4","https://bodymindaerialstudio.life/seed-media/gallery4?v=7"),
        ("gallery5","https://bodymindaerialstudio.life/seed-media/gallery5?v=9"),
        ("gallery2","https://bodymindaerialstudio.life/seed-media/gallery2?v=7"),
        ("competition","https://bodymindaerialstudio.life/static/media/bodymind-competition-double.webp"),
    ]:
        item={"name":name}
        try:
            with urlopen(Request(url,headers={"User-Agent":"BodyMind-QA/1.0"}),timeout=18) as resp:
                data=resp.read(9_000_000)
            img=Image.open(BytesIO(data))
            item.update({"width":img.width,"height":img.height,"bytes":len(data),"format":img.format})
        except Exception as e:
            item["error"]=type(e).__name__
        found.append(item)
    return found

JS="""() => {
const element=(sel)=>{const e=document.querySelector(sel);if(!e)return null;
const b=e.getBoundingClientRect(),c=getComputedStyle(e);
return {x:b.x,y:b.y,width:b.width,height:b.height,
  visibility:c.visibility,display:c.display,opacity:c.opacity,fontSize:c.fontSize,
  position:c.position,objectFit:c.objectFit}};
const img=document.querySelector('.bm-entrance-photo img'),logo=document.querySelector('.site-logo img');
return {width:innerWidth,height:innerHeight,
 scrollWidth:document.documentElement.scrollWidth,
 hero:element('.bm-entrance'),title:element('.bm-entrance h1'),
 photo:element('.bm-entrance-photo img'),cta:element('.bm-entrance-cta'),
 identity:element('.bm-identity'),logo:element('.site-logo img'),
 logoNaturalWidth:logo?.naturalWidth||0,
 media:{naturalWidth:img?.naturalWidth||0,naturalHeight:img?.naturalHeight||0,
 src:img?.getAttribute('src')?.split('?')[0]||null},
 tickerPresent:!!document.querySelector('.achievement-marquee'),
 familyLink:!!document.querySelector('a[href*="area-famiglie"]'),
 competition:!!document.querySelector('.competition-palmares'),
 courses:document.querySelectorAll('.program-card').length,
 hasVenue:!!document.querySelector('#sedi'),
 hasContact:!!document.querySelector('#contatti')
};}"""

async def check_local(browser,width,height,mobile=False):
    context=await browser.new_context(viewport={"width":width,"height":height},device_scale_factor=2,
                                      is_mobile=mobile,has_touch=mobile,locale="it-IT")
    page=await context.new_page()
    js_errors=[]
    page.on("pageerror",lambda err:js_errors.append(str(err)[:140]))
    resp=await page.goto(LOCAL,wait_until="domcontentloaded",timeout=45000)
    assert resp and resp.status==200,f"Local stage response {resp.status if resp else 'none'}"
    await page.locator(".bm-entrance h1").wait_for()
    try:
        await page.wait_for_function("() => !!document.querySelector('.bm-entrance-photo img')?.naturalWidth",timeout=25000)
    except Exception:
        pass
    # The live logo is served from the public BodyMind domain in the
    # isolated CI preview; it may finish after the hero JPEG.
    await page.wait_for_function("() => !!document.querySelector('.site-logo img')?.naturalWidth",timeout=18000)
    await page.wait_for_timeout(250)
    state=await page.evaluate(JS)
    assert state["media"]["naturalWidth"]>=700,"No usable authentic hero still: "+str(state["media"])
    assert state["logoNaturalWidth"]>=200,"Original BodyMind logo failed to load"
    assert state["scrollWidth"]<=width+2,f"Horizontal scroll {width}: "+str(state["scrollWidth"])
    assert state["title"] and state["cta"] and state["logo"]
    assert state["cta"]["width"]>=150 and state["cta"]["height"]>=44
    assert not state["tickerPresent"],"Legacy medal marquee still on hero"
    assert state["courses"]==3 and state["competition"] and state["hasVenue"] and state["hasContact"]
    if mobile:
        assert state["cta"]["y"]+state["cta"]["height"]<=height+4,("Trial CTA not in first viewport",state)
        assert state["photo"]["width"]>=250,"Athlete's image too small at 390px"
        assert state["title"]["fontSize"] not in ("0px","")
    await page.screenshot(path=str(OUT/f"stage01-{width}x{height}.png"),animations="disabled")
    if mobile:
        await page.locator('.bm-identity').scroll_into_view_if_needed()
        await page.screenshot(path=str(OUT/f"stage01-identity-{width}.png"),animations="disabled")
        await page.evaluate("scrollTo(0,0)")
        menu=page.locator("[data-menu]")
        await menu.click()
        assert await menu.get_attribute("aria-expanded")=="true","Mobile menu not opened"
        family_in_menu=page.locator('[data-mobile-menu] a').filter(has_text="Area Famiglie")
        assert await family_in_menu.count()==1
        await menu.click()
        assert await menu.get_attribute("aria-expanded")=="false","Mobile menu not closed"
        await page.locator(".bm-entrance-cta").click()
        assert page.url.endswith("#contatti"),"Trial CTA does not go to contacts"
        await page.emulate_media(reduced_motion="reduce")
        await page.evaluate("scrollTo(0,0)")
        assert await page.locator(".bm-entrance h1").is_visible(),"Title missing in reduce-motion"
    else:
        assert state["cta"]["x"]+state["cta"]["width"]<width
    assert not js_errors,"JS errors "+repr(js_errors)
    REPORT["screens"].append({"viewport":f"{width}x{height}","mobile":mobile,
                               "heroNatural":[state["media"]["naturalWidth"],state["media"]["naturalHeight"]],
                               "ctaVisibleFirstScreen":state["cta"]["y"]+state["cta"]["height"]<=height+4,
                               "horizontalOverflow":False,"menuAndCTA":mobile,
                               "jsErrors":len(js_errors)})
    await context.close()

async def baseline(browser):
    page=await browser.new_page(viewport={"width":390,"height":844},device_scale_factor=2,
                                is_mobile=True,has_touch=True)
    try:
        resp=await page.goto(LIVE,wait_until="domcontentloaded",timeout=50000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT/"baseline-live-390x844.png"),animations="disabled")
        REPORT["live_baseline"]={"HTTP":resp.status if resp else None,"screenshot":True,
                                  "not_live_authenticated":True}
    except Exception as e:
        REPORT["live_baseline"]={"error":type(e).__name__,"screenshot":False}
    finally:
        await page.close()

async def main():
    REPORT["media"]=media_probe()
    async with async_playwright() as p:
        browser=await p.webkit.launch()
        await baseline(browser)
        for width,height,mobile in [(390,844,True),(320,700,True),(430,932,True),(1440,900,False)]:
            await check_local(browser,width,height,mobile)
        await browser.close()
    (OUT/"report.json").write_text(json.dumps(REPORT,indent=2,ensure_ascii=False))
    print("BODYMIND_STAGE01_WEBKIT_PASS "+json.dumps(REPORT,ensure_ascii=False))

asyncio.run(main())
