"""A265 STAGING patch: actual source files on a private, audited COPY only.
No DDL, no DML, no Railway changes. No automatic production deploy.
"""
import argparse, pathlib, hashlib, os, json
from pathlib import Path

def change(s,a,b,label):
    n=s.count(a)
    if n!=1:raise RuntimeError(f'STOP A265 {label}: expected one anchor, found {n}')
    return s.replace(a,b,1)

def run(root):
    root=Path(root).resolve()
    if str(root).startswith('/data/top2_app'):raise RuntimeError('STOP A265: production root forbidden')
    core=root/'core.py';book=root/'routes_contabilita.py';helper=root/'bodymind_a265_cashbook.py'
    if helper.exists():raise RuntimeError('STOP A265: existing module requires review')
    a=core.read_text(encoding='utf-8');b=book.read_text(encoding='utf-8')
    # Fix source of /contabilita being silently hijacked by the expenses form.
    a=change(a,
      "if request.path in ('/uscite','/pagamenti/uscite','/contabilita') and request.method in ('GET','POST'):",
      "# BODYMIND_A265: /contabilita is the authoritative finance ledger, not an alias for expenses.\n    if request.path in ('/uscite','/pagamenti/uscite') and request.method in ('GET','POST'):",
      'conflicting before_request expense shortcut')
    # Turn 900px overflow table into readable rows on mobile. No data filtered or deleted.
    a=change(a,"<div class='bmout11-table'><table>","<div class='bmout11-table' id='movimenti-uscite'><table>",'expense anchor')
    a=change(a,'"<tr><td>"+e(str(r[\'data\']))+"</td>"',
               '"<tr><td data-label=\'Data\'>"+e(str(r[\'data\']))+"</td>"','expense date cell')
    for old,new,label in [
        ('"<td><b>"+e(str(r[\'descrizione\']))','"<td data-label=\'Causale\'><b>"+e(str(r[\'descrizione\']))','description'),
        ('"<td><b>€ "+e(_eur(r[\'importo\']))','"<td data-label=\'Importo\'><b>€ "+e(_eur(r[\'importo\']))','amount'),
        ('"<td>"+e(str(r[\'metodo\'] or \'\'))','"<td data-label=\'Metodo\'>"+e(str(r[\'metodo\'] or \'\'))','method'),
        ('"<td><div class=\'bmout11-files\'>"+att','"<td data-label=\'Giustificativo\'><div class=\'bmout11-files\'>"+att','attachment'),
        ('"<td><a class=\'bmout11-edit\'','"<td data-label=\'Azioni\'><a class=\'bmout11-edit\'','edit'),
    ]:a=change(a,old,new,label)
    # Links to the same records; no new route, GET filter for bank expenses only.
    a=change(a,
     "    rows=conn.execute(\"SELECT * FROM bodymind_uscite ORDER BY data DESC,id DESC LIMIT 300\").fetchall()",
     "    selected_method=(request.args.get('metodo') or '').strip().casefold()\n"
     "    if selected_method not in ('','bonifico'):selected_method=''\n"
     "    if selected_method=='bonifico':\n"
     "        rows=conn.execute(\"SELECT * FROM bodymind_uscite WHERE LOWER(TRIM(COALESCE(metodo,''))) IN ('bonifico','bonifico bancario','sepa','banca','bank transfer','iban') ORDER BY data DESC,id DESC LIMIT 300\").fetchall()\n"
     "    else:rows=conn.execute(\"SELECT * FROM bodymind_uscite ORDER BY data DESC,id DESC LIMIT 300\").fetchall()",
     'bank outgoing filter')
    a=change(a,
      "      <div class='bmout11-table' id='movimenti-uscite'>",
      "      <div class='bmout11-filters' aria-label='Filtra uscite'><a href='/pagamenti/uscite#movimenti-uscite'>Tutte le uscite</a><a href='/pagamenti/uscite?metodo=bonifico#movimenti-uscite'>Solo bonifici</a></div>\n      <div class='bmout11-table' id='movimenti-uscite'>",
      'expense filters')
    css='''
      /* BODYMIND_A265_MOBILE_EXPENSES: no 900px horizontal ledger on phones */
      .bmout11 .bmout11-filters{{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 2px}}
      .bmout11 .bmout11-filters a{{border:1px solid #466078;border-radius:9px;padding:9px 12px;color:#d9eaf9;text-decoration:none;font-size:13px;font-weight:750}}
      @media(max-width:720px){{
        .bmout11 .bmout11-table{{overflow:visible;max-width:100%}}
        .bmout11 .bmout11-table table{{display:block;min-width:0!important;width:100%;border:0}}
        .bmout11 .bmout11-table thead{{display:none}}
        .bmout11 .bmout11-table tbody{{display:grid;gap:10px}}
        .bmout11 .bmout11-table tr{{display:block;min-width:0;padding:7px 11px;background:#16283a;border:1px solid #3c5068;border-radius:13px}}
        .bmout11 .bmout11-table td{{display:grid;grid-template-columns:minmax(90px,35%) minmax(0,1fr);gap:8px;min-width:0;padding:8px 0;border-bottom:1px solid #30465e;overflow-wrap:anywhere}}
        .bmout11 .bmout11-table td:last-child{{border:0}}
        .bmout11 .bmout11-table td::before{{content:attr(data-label);color:#b6c9dd;font-weight:800;font-size:12px}}
        .bmout11 .bmout11-table .bmout11-files{{min-width:0}}
        .bmout11 .bmout11-table .bmout11-edit{{width:max-content;max-width:100%}}
        .bmout11 .bmout11-head>strong{{white-space:normal}}
        .bmout11 .bmout11-form{{grid-template-columns:1fr}}
      }}
'''
    a=change(a,"    </style>\n    \"\"\"\n    return layout(html)\n\n\n@app.before_request\ndef _bodymind_expense_entry_v11():",
      css+"    </style>\n    \"\"\"\n    return layout(html)\n\n\n@app.before_request\ndef _bodymind_expense_entry_v11():",
      'expense CSS close')
    # Ledger route /contabilita: use same canonical finance snapshot (A237).
    b=change(b,"   from .bodymind_a237_finance_truth import snapshot as a253_snapshot",
        "   from .bodymind_a237_finance_truth import snapshot as a253_snapshot\n   from .bodymind_a265_cashbook import build as a265_build, render as a265_render",'ledger import')
    b=change(b,
      "   if check_in!=totale_entrate or check_out!=totale_uscite:\n       conn.close()\n       return layout(alert_html('Movimenti e totali contabili non coincidono. Operazione sospesa.','error')),409",
      "   if check_in!=totale_entrate or check_out!=totale_uscite:\n       conn.close()\n       return layout(alert_html('Movimenti e totali contabili non coincidono. Operazione sospesa.','error')),409\n"
      "   try:\n       a265_markup=a265_render(a265_build(conn,finance))\n"
      "   except (ValueError,RuntimeError,KeyError) as exc:\n       conn.close()\n       return layout(alert_html('Verifica contabile necessaria: '+str(exc),'error')),409",
      'A265 ledger reconciliation')
    b=change(b,'   <div class="card">\n       <div class="page-head">',
      "   {a265_markup}\n   <div class=\"card\">\n       <div class=\"page-head\">",'summary insertion')
    b=change(b,'<div style=\'overflow-x:auto\'><table><tr><th>Tipo</th><th>Categoria</th><th>Descrizione</th><th>Importo</th><th>Data</th><th>Origine</th><th>Azioni</th></tr>',
      '<div class=\'a265-ledger-scroll\'><table class=\'a265-ledger\'><tr><th>Tipo</th><th>Categoria</th><th>Descrizione</th><th>Importo</th><th>Metodo</th><th>Data</th><th>Origine</th><th>Azioni</th></tr>',
      'ledger table column titles')
    b=change(b,'   for r in rows:\n       automatico =',
      "   payment_methods={int(x['id']):str(x['metodo_pagamento'] or '') for x in conn.execute('SELECT id,metodo_pagamento FROM pagamenti')}\n   manual_methods=a253_methods(conn)\n   for r in rows:\n       automatico =",
      'ledger method lookup')
    b=change(b,
      "       origine = 'Uscita registrata' if r.get('_a250_spesa') else ('Pagamento automatico' if automatico else 'Manuale verificato')",
      "       origine = 'Uscita registrata' if r.get('_a250_spesa') else ('Pagamento automatico' if automatico else 'Manuale verificato')\n"
      "       metodo=(str(r.get('_a250_metodo') or '') if r.get('_a250_spesa') else\n"
      "               (str(payment_methods.get(int(r['pagamento_id']),'')) if r.get('pagamento_id') else str(manual_methods.get(int(r['id']),'da verificare'))))",
      'ledger method details')
    b=change(b,
      "       actions = f\"\"\"\n       <div class='actions'>",
      "       actions = f\"\"\"\n       <div class='actions'>",'do not patch orphan guard')
    # Expense rows link out to the actual expense editor instead of an irrelevant 'Bloccato'.
    b=change(b,
      '"<span class=\'small-muted\'>Bloccato</span>" if automatico else f"""',
      '((f"<a href=\'/pagamenti/uscite?modifica={r[\'id\']}#movimenti-uscite\'>Apri uscita</a>") if r.get(\'_a250_spesa\') else "<span class=\'small-muted\'>Da Pagamenti</span>") if automatico else f"""',
      'expense detail links')
    for old,new,label in [
      ("<tr>\n           <td>{e(r['tipo'])}</td>","<tr>\n           <td data-label='Tipo'>{e(r['tipo'])}</td>",'ledger type'),
      ("<td>{e(r['categoria'])}</td>","<td data-label='Categoria'>{e(r['categoria'])}</td>",'ledger category'),
      ("<td>{e(r['descrizione'])}</td>","<td data-label='Descrizione'>{e(r['descrizione'])}</td>",'ledger description'),
      ("<td>{euro(r['importo'])}</td>","<td data-label='Importo'>{euro(r['importo'])}</td>\n           <td data-label='Metodo'>{e(metodo)}</td>",'ledger amount+method'),
      ("<td>{e(format_display_date(r['data']))}</td>","<td data-label='Data'>{e(format_display_date(r['data']))}</td>",'ledger date'),
      ("<td>{origine}</td>","<td data-label='Origine'>{origine}</td>",'ledger origin'),
      ("<td>{actions}</td>","<td data-label='Azioni'>{actions}</td>",'ledger action'),
    ]:b=change(b,old,new,label)
    b=change(b,'   html_out += "</table></div></div>"',
      '''   html_out += """</table></div></div>
    <style id='a265-ledger-mobile'>
    .a265-ledger-scroll{max-width:100%;overflow-x:auto}
    .a265-ledger{min-width:850px}
    @media(max-width:720px){
      .a265-ledger-scroll{overflow:visible}
      .a265-ledger{display:block;width:100%;min-width:0!important}
      .a265-ledger tr:first-child{display:none}
      .a265-ledger tr{display:block;min-width:0;border:1px solid #43566d;border-radius:12px;margin:9px 0;padding:9px 12px;background:#172b40}
      .a265-ledger td{display:grid;grid-template-columns:90px minmax(0,1fr);gap:9px;min-width:0;padding:8px 0;overflow-wrap:anywhere;border-bottom:1px solid #32475e}
      .a265-ledger td::before{content:attr(data-label);font-weight:750;color:#c0cddd;font-size:12px}
      .a265-ledger td:last-child{border:0}
    }
    </style>"""''', 'ledger responsive CSS')
    for name,code in [('core.py',a),('routes_contabilita.py',b)]:compile(code,name,'exec')
    helper_source=(Path(__file__).parent/'bodymind_a265_cashbook.py').read_bytes()
    compile(helper_source,str(helper),'exec')
    # Write only after all file checks/compilation; this is a staged clone, not a live deployment.
    for target,code in [(core,a),(book,b)]:
        tmp=target.with_suffix(target.suffix+'.a265-tmp');tmp.write_text(code,encoding='utf-8');os.replace(tmp,target)
    helper.write_bytes(helper_source)
    return {f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in ('core.py','routes_contabilita.py','bodymind_a265_cashbook.py')}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True); args=p.parse_args()
    print(json.dumps(run(args.root),indent=2))