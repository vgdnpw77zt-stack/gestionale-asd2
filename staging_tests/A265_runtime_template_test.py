"""Actual production HTML f-string evaluation, without importing the web app or DB."""
from pathlib import Path
from html import escape
import ast
core=Path(__file__).parent/'runtime/asd_app/core.py'
mod=ast.parse(core.read_text(encoding='utf8'))
fun=next(x for x in mod.body if isinstance(x,ast.FunctionDef) and x.name=='_bodymind_uscite_v11_impl')
node=next(x for x in ast.walk(fun) if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='html' for t in x.targets))
assert isinstance(node.value,ast.JoinedStr),type(node.value)
needed={x.value.id for x in ast.walk(node.value) if isinstance(x,ast.FormattedValue) and isinstance(x.value,ast.Name)}
assert 'display' not in needed and 'border' not in needed, 'Raw CSS parsed as Python expression!'
context={
 'form_data':{'id':1,'data':'2026-10-18','descrizione':'Bonifico presidente','categoria':'Rimborsi','importo':'80','metodo':'bonifico','note':'','allegato_nome':''},
 'e': lambda x: escape(str(x),quote=True), 'csrf_token':lambda:'test-csrf', 'total':80,
 '_eur':lambda x: '80,00', 'msg':'','attached':'','table_rows':'<tr><td data-label="Metodo">bonifico</td></tr>',
}
expr=ast.fix_missing_locations(ast.Expression(body=node.value))
rendered=eval(compile(expr,str(core),'eval'),{'__builtins__':{'str':str}, **context}, context)
assert '.bmout11 .bmout11-filters{display:flex;' in rendered
assert '.bmout11 .bmout11-filters a{border:' in rendered
assert 'Bonifico presidente' in rendered
assert 'data-label="Metodo"' in rendered
assert '{{' not in rendered.split('BODYMIND_A265_MOBILE_EXPENSES:',1)[1].split('</style>')[0]
print('A265 RUNTIME TEMPLATE PASS: expense page renders as Python f-string; mobile CSS and bank method present.')