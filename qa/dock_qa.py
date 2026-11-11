import asyncio,json,pathlib,sys
from playwright.async_api import async_playwright
mode=sys.argv[1] if len(sys.argv)>1 else 'candidate'
out=pathlib.Path('dock-evidence');out.mkdir(exist_ok=True)
async def main():
 async with async_playwright() as p:
  b=await p.webkit.launch()
  results=[]
  for w,h in [(375,667),(390,844),(430,932),(1440,1000)]:
   for variant in (['before','candidate'] if mode=='candidate' else ['online']):
    c=await b.new_context(viewport={'width':w,'height':h},is_mobile=w<600,has_touch=w<600)
    page=await c.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    if variant=='candidate':
     for name in ['site.css','site.js']:
      async def route(r,name=name):
       await r.fulfill(status=200,content_type='text/css' if name.endswith('css') else 'application/javascript',body=pathlib.Path('site/static/'+name).read_text())
      await page.route('**/static/'+name+'*',route)
    r=await page.goto('https://bodymindaerialstudio.life/',wait_until='networkidle')
    await page.evaluate('document.fonts.ready')
    await page.wait_for_timeout(1200)
    assert r.status==200
    if w<600: assert await page.locator('.mobile-action-dock').is_visible()
    await page.screenshot(path=str(out/f'{variant}-{w}-home.png'))
    if w<600:
     await page.locator('.menu-btn').click()
     await page.locator('.mobile-menu a[href="#contatti"]').click()
    else: await page.locator('.header-cta').click()
    await page.wait_for_timeout(1400)
    await page.screenshot(path=str(out/f'{variant}-{w}-contacts.png'))
    dock=await page.locator('.mobile-action-dock').is_visible()
    if variant!='before' and w<600:
     assert not dock
     assert await page.locator('.mobile-action-dock').evaluate('e=>e.inert')
    for sel,label in [('.program-card.p2','competition'),('.program-card.p3','show'),('#kids','kids')]:
     await page.locator(sel).scroll_into_view_if_needed()
     await page.wait_for_timeout(800)
     await page.screenshot(path=str(out/f'{variant}-{w}-{label}.png'))
     if variant!='before' and w<600: assert not await page.locator('.mobile-action-dock').is_visible()
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    await page.evaluate("scrollTo({top:0,behavior:'instant'})")
    await page.wait_for_timeout(1000)
    if w<600:
     assert await page.locator('.mobile-action-dock').is_visible()
     await page.locator('.mobile-action.primary').click()
     await page.wait_for_timeout(1200)
     assert await page.evaluate("location.hash==='#contatti'")
    assert not errors,errors
    results.append(dict(width=w,variant=variant,dock_in_contacts=dock,errors=errors))
    await c.close()
  await b.close()
  (out/'results.json').write_text(json.dumps(results,indent=2))
asyncio.run(main())
