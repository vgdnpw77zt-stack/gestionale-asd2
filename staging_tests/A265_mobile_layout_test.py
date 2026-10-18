from pathlib import Path
import re
from playwright.sync_api import sync_playwright
root=Path(__file__).parent/'runtime/asd_app'
core=(root/'core.py').read_text()
book=(root/'routes_contabilita.py').read_text()
css1=core.split('/* BODYMIND_A265_MOBILE_EXPENSES:',1)[1].split('    </style>',1)[0]
css1='/* BODYMIND_A265_MOBILE_EXPENSES:'+css1
css1=css1.replace('{{','{').replace('}}','}')
css2=book.split("<style id='a265-ledger-mobile'>",1)[1].split('</style>',1)[0]
html='''<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}body{margin:0;background:#101c2b;color:#f4f7fb;font:16px Arial,sans-serif}.container{max-width:1152px;margin:auto;padding:14px}
.bmout11{margin:14px 0;padding:20px;background:#081626;border:1px solid #2b445b;border-radius:20px}.bmout11-table{overflow:auto}.bmout11-table table{min-width:900px;width:100%;border-collapse:collapse}.bmout11-table th,.bmout11-table td{padding:10px;border-bottom:1px solid #2b445b;text-align:left}
.bmout11-files{display:flex;flex-wrap:wrap;gap:7px}.a265-ledger{min-width:850px;width:100%;border-collapse:collapse}.a265-ledger-scroll{overflow:auto}
'''+css1+css2+'''</style></head><body><div class="container">
<h1>Contabilità</h1><section class="bmout11"><h2>Uscite</h2><div class="bmout11-table"><table><thead><tr><th>Data</th><th>Uscita</th><th>Importo</th><th>Metodo</th><th>Giustificativo</th><th>Azioni</th></tr></thead><tbody><tr><td data-label="Data">2026-10-18</td><td data-label="Causale">Bonifico effettuato al presidente</td><td data-label="Importo">80,00 €</td><td data-label="Metodo">bonifico</td><td data-label="Giustificativo"><div class="bmout11-files">Documento</div></td><td data-label="Azioni"><a href="#">Apri uscita</a></td></tr></tbody></table></div></section>
<div class="a265-ledger-scroll"><table class="a265-ledger"><tr><th>Tipo</th><th>Categoria</th><th>Descrizione</th><th>Importo</th><th>Metodo</th><th>Data</th><th>Origine</th><th>Azioni</th></tr><tr><td data-label="Tipo">uscita</td><td data-label="Categoria">Rimborsi</td><td data-label="Descrizione">Bonifico effettuato al presidente</td><td data-label="Importo">80,00 €</td><td data-label="Metodo">bonifico</td><td data-label="Data">18/10/2026</td><td data-label="Origine">Uscita registrata</td><td data-label="Azioni"><a href="#">Apri uscita</a></td></tr></table></div></div></body></html>'''
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for w in (375,390,428,768,1024,1152,1280,1366):
        page=browser.new_page(viewport={'width':w,'height':850},device_scale_factor=1)
        page.set_content(html)
        overflow=page.evaluate('document.documentElement.scrollWidth - innerWidth')
        if w<=720:
            assert page.locator('.bmout11-table td[data-label="Metodo"]').is_visible(), 'method hidden'
            assert page.locator('.bmout11-table td[data-label="Causale"]').is_visible()
            td=page.locator('.bmout11-table td[data-label="Metodo"]').bounding_box()
            assert td and td['x']+td['width']<=w+1,(w,td)
            assert page.locator('.a265-ledger td[data-label="Metodo"]').is_visible()
        assert overflow<=1,(w,overflow)
        print('A265 VIEW',w,'overflow',overflow,'bank expense and method visible')
        page.close()
    browser.close()
print('A265 LAYOUT PASS')