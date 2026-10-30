import asyncio, base64, json, os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    token=Path('/tmp/bm-family-token').read_text().strip()
    assert token and len(token)<200
    async with async_playwright() as p:
        browser=await p.webkit.launch()
        page=await browser.new_page(**p.devices['iPhone 13'])
        response=await page.goto('https://app.bodymindaerialstudio.life/app-tesserato/'+token,wait_until='networkidle',timeout=60000)
        assert response.status==200
        await page.locator('.hero h1').wait_for()
        await page.wait_for_timeout(1500)
        state=await page.evaluate("""() => {
          const sels=['.hero','.hero-media','.hero-content','.hero-intro','#familyHeroVideo','main.main','.bottom-nav'];
          const result={w:innerWidth,h:innerHeight,media:matchMedia('(max-width:760px)').matches,nodes:[],rules:[]};
          for(const sel of sels){
            const e=document.querySelector(sel);if(!e)continue;
            const s=getComputedStyle(e),r=e.getBoundingClientRect();
            result.nodes.push({sel,w:r.width,h:r.height,top:r.top,left:r.left,position:s.position,z:s.zIndex,display:s.display,background:s.background,animation:getComputedStyle(e,'::before').animationName});
          }
          function rules(rs,owner,active=true){
            for(const r of rs){
              if(r.cssRules){rules(r.cssRules,owner,active && (!r.conditionText || !r.constructor.name.includes('Media') || matchMedia(r.conditionText).matches));continue;}
              if(!active||!r.selectorText)continue;
              try{
                if(sels.some(sel=>document.querySelector(sel)?.matches(r.selectorText)) && ['position','display','width','height','min-height','max-height','background','z-index','animation','transform'].some(k=>r.style.getPropertyValue(k)))
                result.rules.push({owner,selector:r.selectorText,css:r.style.cssText});
              }catch(e){}
            }
          }
          for(const s of document.styleSheets){try{rules(s.cssRules,s.ownerNode.id || (s.href?new URL(s.href).pathname:'inline'));}catch(e){}}
          const v=document.querySelector('#familyHeroVideo');result.video={paused:v.paused,time:v.currentTime,w:v.videoWidth,h:v.videoHeight,ready:v.readyState};
          return result;
        }""")
        print('A362_LIVE_STATE '+json.dumps(state))
        screenshot=await page.screenshot(type='jpeg',quality=75)
        print('A362_SCREENSHOT '+base64.b64encode(screenshot).decode())
        await page.wait_for_timeout(2500)
        print('A362_VIDEO_TIME '+str(await page.locator('#familyHeroVideo').evaluate('(e)=>e.currentTime')))
        await browser.close()
asyncio.run(main())
