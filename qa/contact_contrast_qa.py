import asyncio, json, pathlib, sys, io
from PIL import Image
from playwright.async_api import async_playwright

MODE=sys.argv[1] if len(sys.argv)>1 else 'candidate'
OUT=pathlib.Path('contact-qa-'+MODE); OUT.mkdir(exist_ok=True)
def luminance(rgb):
    c=[v/255 for v in rgb[:3]]
    c=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c]
    return .2126*c[0]+.7152*c[1]+.0722*c[2]
def contrast(a,b):
    x,y=sorted([luminance(a),luminance(b)])
    return (y+.05)/(x+.05)

async def main():
  results=[]
  async with async_playwright() as p:
    browser=await p.webkit.launch()
    for width,height in [(375,667),(390,844),(430,932),(1440,1000)]:
      variants=['before','after'] if MODE=='candidate' else ['online']
      for variant in variants:
        ctx=await browser.new_context(viewport={'width':width,'height':height},is_mobile=width<600,has_touch=width<600,device_scale_factor=1)
        page=await ctx.new_page(); errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        if variant=='after':
          await page.route('**/static/sunrise.css*',lambda r:r.fulfill(status=200,content_type='text/css',body=pathlib.Path('site/static/sunrise.css').read_text()))
        response=await page.goto('https://bodymindaerialstudio.life/',wait_until='networkidle',timeout=90000)
        await page.evaluate('document.fonts.ready')
        await page.wait_for_function("getComputedStyle(document.querySelector('.hero-copy h1')).opacity==='1'")
        home=await page.evaluate("""() => {const k=document.querySelector('.kicker').getBoundingClientRect(),m=document.querySelector('.achievement-marquee').getBoundingClientRect(),h=document.querySelector('.hero-copy h1').getBoundingClientRect(),v=document.querySelector('video');return {gap:k.top-m.bottom,titleGap:h.top-k.bottom,overflow:document.documentElement.scrollWidth-innerWidth,videoPaused:v.paused}}""")
        assert response.status==200 and home['overflow']==0
        if width<600: assert home['gap']>=8 and home['titleGap']>=12
        if width<600:
          await page.locator('.menu-btn').click()
          await page.locator('.mobile-menu a[href="#contatti"]').click()
        else: await page.locator('.header-cta').click()
        await page.wait_for_function("location.hash==='#contatti'")
        await page.wait_for_timeout(1800)
        await page.screenshot(path=str(OUT/f'{variant}-{width}.png'))
        labels=[]
        for locator in ['#contatti > .section-label','#contatti .contact-links small']:
          for el in await page.locator(locator).all():
            await el.evaluate("e=>e.scrollIntoView({block:'center',behavior:'instant'})"); await page.wait_for_timeout(600)
            data=await el.evaluate("e=>({text:e.textContent,color:getComputedStyle(e).color,box:e.getBoundingClientRect().toJSON()})")
            rgb=[int(x) for x in data['color'].replace('rgb(','').replace(')','').split(',')]
            await el.evaluate("e=>e.style.visibility='hidden'")
            box=data['box']; clip={k:box[k] for k in ['x','y','width','height']}
            png=await page.screenshot()
            await el.evaluate("e=>e.style.removeProperty('visibility')")
            im=Image.open(io.BytesIO(png)).convert('RGB').crop((int(box['x']),int(box['y']),int(box['right']),int(box['bottom'])))
            data['minimum_contrast']=min(contrast(rgb,c) for c in im.getdata())
            if variant!='before': assert data['minimum_contrast']>=4.5,data
            labels.append(data)
        links=await page.locator('#contatti .contact-links a').evaluate_all("es=>es.map(e=>({text:e.textContent.trim(),href:e.getAttribute('href')}))")
        assert links and all(l['href'] for l in links)
        assert not errors, errors
        css=await page.locator('link[rel=stylesheet]').evaluate_all('es=>es.map(e=>e.href)')
        if MODE=='online': assert any('a351-contact-contrast-20261111' in u for u in css)
        results.append(dict(width=width,variant=variant,home=home,labels=labels,links=links,errors=errors))
        await ctx.close()
    await browser.close()
  if MODE=='candidate':
    for i in range(0,len(results),2):
      a,b=results[i:i+2]
      assert a['links']==b['links']
      assert [x['box'] for x in a['labels']]==[x['box'] for x in b['labels']]
  (OUT/'results.json').write_text(json.dumps(results,indent=2))
  print(json.dumps([{'width':r['width'],'variant':r['variant'],'contrast':[round(l['minimum_contrast'],2) for l in r['labels']]} for r in results]))
asyncio.run(main())
