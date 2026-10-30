import asyncio, base64, json, os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    token=Path('/tmp/bm-family-token').read_text().strip()
    assert token and len(token)<200
    async with async_playwright() as p:
        browser=await p.webkit.launch()
        page=await browser.new_page(**p.devices['iPhone 13'])
        if os.environ.get('A362_PREVIEW')=='1':
            import sys,re
            sys.path.insert(0,str(Path('bootstrap').resolve()))
            from family_a362_runtime import compose,clean_response_markup
            async def preview(route):
                if route.request.resource_type!='document':
                    await route.continue_();return
                response=await route.fetch()
                html=await response.text()
                if 'familyHeroVideo' not in html:
                    await route.fulfill(response=response);return
                styles=list(re.finditer(r'<style\\b[^>]*>.*?</style>',html,re.S|re.I))
                first=styles[0].group(0)
                html=re.sub(r'<style\\b[^>]*>.*?</style>',lambda m:first if m.start()==styles[0].start() else '',html,flags=re.S|re.I)
                def scripts(m):
                    v=m.group(0)
                    return v if any(k in v.split('>',1)[0] for k in ('bodymind-media-links-a350','bodymind-a345-video','bodymind-a349-native-ratio')) or v.startswith("<script>\\n(()=>{'use strict';const track=") else ''
                html=re.sub(r'<script\\b[^>]*>.*?</script>',scripts,html,flags=re.S|re.I)
                html=re.sub(r'<body\\b[^>]*>','<body>',html,count=1)
                html=clean_response_markup(compose(html,verify=False))
                await route.fulfill(response=response,body=html)
            await page.route('**/app-tesserato/**',preview)
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
              if(r.cssRules && !r.selectorText){rules(r.cssRules,owner,active && (!r.conditionText || !r.constructor.name.includes('Media') || matchMedia(r.conditionText).matches));continue;}
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
        Path('webkit-iphone.jpg').write_bytes(screenshot)
        Path('webkit-state.json').write_text(json.dumps(state,indent=2))
        await page.wait_for_timeout(2500)
        print('A362_VIDEO_TIME '+str(await page.locator('#familyHeroVideo').evaluate('(e)=>e.currentTime')))
        if os.environ.get('A362_EXPECT')=='1':
            assert await page.locator('body').get_attribute('data-bodymind-family')=='A362'
            assert await page.locator('style').count()==1
            assert await page.locator('#bodymind-a361-probe').count()==0
            video=page.locator('#familyHeroVideo')
            v=await video.bounding_box(); intro=await page.locator('.hero-intro').bounding_box()
            assert intro['y']>=v['y']+v['height']-1, 'Welcome overlaps film'
            cloud=page.locator('.bm362-cloud').first
            a=await cloud.evaluate('(e)=>getComputedStyle(e).transform')
            await page.wait_for_timeout(1800)
            b=await cloud.evaluate('(e)=>getComputedStyle(e).transform')
            assert a!=b,'Clouds are static'
            await page.locator('#familyHeroPlayback').click()
            assert await video.evaluate('(e)=>e.paused')
            await page.locator('#familyHeroPlayback').click()
            await page.wait_for_timeout(600)
            assert not await video.evaluate('(e)=>e.paused')
            await page.locator('.bm362-menu').click()
            assert await page.locator('.bm362-menu').get_attribute('aria-expanded')=='true'
            await page.locator('.bottom-nav a[href="#documenti"]').click()
            assert await page.locator('#documenti').is_visible()
            assert await page.locator('.bm362-menu').get_attribute('aria-expanded')=='false'
            for target in ('corsi','pagamenti','media','top'):
                await page.locator('.bm362-menu').click()
                await page.locator('.bottom-nav a[href="#'+target+'"]').click()
                await page.wait_for_timeout(500)
                assert page.url.endswith('#'+target)
            assert await page.locator('.bm351-private-album').count()==1
            assert await page.locator('.upload input[name="csrf_token"]').count()>=1
            assert await page.locator('.bm362-studio a').count()==1
            assert await page.locator('.receipts a').count()>0
            await page.locator('#top').scroll_into_view_if_needed()
            await page.screenshot(path='webkit-iphone-after.jpg',type='jpeg',quality=85)
            print('A362_AUTHENTICATED_WEBKIT_CHECKS_PASS')
        await browser.close()
asyncio.run(main())

