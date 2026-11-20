#!/usr/bin/env python3
"""A378 synthetic WebKit regression. No family credentials, DB or protected records.
The actual authenticated page still requires separate visual acceptance.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE=(ROOT/'bootstrap/family_a362_base.css').read_text()
SCENE=(ROOT/'bootstrap/family_a362_scene.css').read_text()
NAV=(ROOT/'bootstrap/family_a362_navigation.js').read_text()
RUNTIME=(ROOT/'bootstrap/family_a362_runtime.py').read_text()
DOCKER=(ROOT/'Dockerfile').read_text()
assert 'A378 — BODYMIND' in SCENE
assert 'data-bodymind-family="A362"' in RUNTIME
assert "X-BodyMind-Family-Release']='A363'" in RUNTIME
assert 'bootstrap/family_a362_scene.css' in DOCKER
assert 'bootstrap/family_a362_navigation.js' in DOCKER
assert 'bm350-gallery-footer' in NAV and 'bm351-private-album' in NAV
assert 'setOpen(mobile.matches)' in NAV
assert 'SOURCE_SHA=' in RUNTIME and 'TEMPLATE_SHA=' in RUNTIME

HTML='''<!doctype html><html lang="it"><head>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>'''+BASE+SCENE+'''</style></head><body data-bodymind-family="A362">
<section class="hero" id="top" aria-labelledby="heroTitle">
 <div class="bm362-sky"><div class="bm362-cloud"></div><div class="bm362-cloud bm362-cloud--near"></div><div class="bm362-stars"></div><svg class="bm362-waves" viewBox="0 0 800 400"><path d="M0 0Q400 250 800 300"/></svg></div>
 <div class="hero-media"><video class="family-hero-video" muted playsinline loop></video></div>
 <div class="frame hero-content"><div class="hero-intro"><span class="eyebrow">AREA ALLIEVE & FAMIGLIE</span>
 <h1 id="heroTitle">Ciao, atleta</h1><p>Qui trovi corsi, pagamenti, documenti e i momenti piu belli.</p>
 <a class="pill" href="#corsi">Scopri il tuo percorso →</a>
 <button class="hero-playback" type="button">Pausa video</button></div></div>
</section>
<main class="frame main">
 <div class="bm362-sky bm362-sky--main"><div class="bm362-cloud"></div><div class="bm362-stars"></div></div>
 <div class="stats"><a class="stat" href="#corsi"><span class="icon">◈</span><div class="stat-copy"><small>Corso attuale</small><strong>Adulti</strong><em>Vai al tuo corso</em></div></a>
 <a class="stat" href="#pagamenti"><span class="icon">€</span><div class="stat-copy"><small>Stato pagamenti</small><strong class="ok">Pagato</strong><em>Apri pagamenti</em></div></a>
 <a class="stat" href="#pagamenti"><span class="icon">▤</span><div class="stat-copy"><small>Certificato medico</small><strong>Valido</strong></div></a>
 <a class="stat" href="#corsi"><span class="icon">✓</span><div class="stat-copy"><small>Presenze</small><strong>6</strong></div></a></div>
 <section id="media" class="section"><div class="section-heading"><h2>Vivi BodyMind</h2></div><div class="media-track"><div class="media-card">Galleria originale</div></div></section>
 <section id="corsi" class="section"><div class="section-heading"><h2>Le mie presenze</h2></div>
 <div class="panel"><div class="bm365-inline"><div class="bm364-family-shell"><div class="bm364-family-intro"><h1>Il tuo mese in volo</h1></div><form class="bm364-month-form"><select aria-label="Mese"><option>Novembre 2026</option></select><button type="button">Visualizza</button></form><div class="bm364-family-summary">5 presenze registrate</div><div class="bm364-family-day">Presente</div></div></div></div></section>
 <section id="pagamenti" class="section"><div class="section-heading"><h2>Le mie quote e ricevute</h2></div><div class="panel"><div class="settled-card"><strong>Pagato</strong></div><div class="payment-box">Nessun pagamento da effettuare</div><div class="receipt">Ricevuta PDF</div><form class="upload"><input aria-label="Carica documento"></form></div></section>
 <section class="bm362-studio"><div><strong>I miei momenti in volo</strong><p>Il tuo album privato</p></div><a class="pill" href="#media">Album</a></section>
</main>
<nav class="bottom-nav" aria-label="Navigazione famiglia">
<a href="#top"><span>⌂</span>Home</a><a href="#corsi"><span>◷</span>Presenze</a><a href="#pagamenti"><span>€</span>Quote</a><a href="#media"><span>▣</span>Media</a><a href="#pagamenti"><span>▤</span>Documenti</a></nav>
<script>'''+NAV+'''</script></body></html>'''

async def run():
    async with async_playwright() as p:
        browser=await p.webkit.launch()
        for width,height in [(320,640),(375,667),(390,664),(390,844),(430,932),(768,900),(1440,900)]:
            page=await browser.new_page(viewport={'width':width,'height':height},
                 device_scale_factor=2,is_mobile=(width<500),has_touch=(width<500))
            await page.set_content(HTML,wait_until='load')
            await page.wait_for_timeout(250)
            data=await page.evaluate("""() => {
              const get=s=>document.querySelector(s);
              const box=s=>get(s).getBoundingClientRect();
              const style=s=>getComputedStyle(get(s));
              return {overflow:document.documentElement.scrollWidth,
                heroHeight:box('.hero').height,
                heroVideoFilter:style('.family-hero-video').filter,
                videoVisible:style('.family-hero-video').display !== 'none',
                coursesOrder:Number(style('#corsi').order),
                feesOrder:Number(style('#pagamenti').order),
                mediaOrder:Number(style('#media').order),
                dockDisplay:style('.bottom-nav').display,
                dockInert:get('.bottom-nav').inert,
                dockCount:get('.bottom-nav').querySelectorAll('a').length,
                menuDisplay:style('.bm362-menu').display,
                selectWidth:box('.bm364-month-form select').width,
                selectRight:box('.bm364-month-form select').right,
                formRight:box('.bm364-month-form').right,
                formButtonHeight:box('.bm364-month-form button').height,
                firstCardBackground:style('.stat').backgroundImage,
                headerColor:style('.hero h1').color,
                bodyPaddingBottom:parseFloat(style('body').paddingBottom)}; }""")
            assert data['overflow']<=width+2,(width,'overflow',data)
            assert data['videoVisible'] and data['heroVideoFilter']=='none',(width,data)
            assert (data['coursesOrder'],data['feesOrder'],data['mediaOrder'])==(1,2,3),(width,'priority order',data)
            assert data['selectRight']<=data['formRight']+2,(width,'month selector truncated',data)
            assert data['formButtonHeight']>=43,(width,'month button too small',data)
            assert '59, 33, 55' in data['firstCardBackground'],(width,'not theatrical plum',data)
            if width<=760:
                assert 560<=data['heroHeight']<=700,(width,'uncompact hero',data)
                assert data['dockCount']==5 and not data['dockInert'],(width,'inaccessible dock',data)
                assert data['dockDisplay']=='flex' and data['menuDisplay']=='none',(width,'floating menu',data)
                assert data['bodyPaddingBottom']>=100,(width,'bottom content hidden',data)
            else:
                assert data['heroHeight']>=650,(width,'desktop cinematic hero',data)
                assert data['menuDisplay']!='none',(width,'desktop menu unexpectedly removed',data)
            await page.locator('.hero .pill').click()
            assert page.url.endswith('#corsi'),(width,'course CTA broken')
            if width<=760:
                assert not await page.locator('.bottom-nav').evaluate('(e)=>e.inert'),(width,'dock hidden after navigation')
            print('A378 SYNTHETIC WEBKIT PASS',width,height,'hero',round(data['heroHeight']))
            await page.close()
        page=await browser.new_page(viewport={'width':390,'height':844},reduced_motion='reduce')
        await page.set_content(HTML,wait_until='load')
        assert await page.locator('.bm362-cloud').first.evaluate('(e)=>getComputedStyle(e).animationName')=='none'
        await browser.close()
        print('A378 SOURCE, UI AND REDUCED MOTION CONTRACT PASS')
asyncio.run(run())
