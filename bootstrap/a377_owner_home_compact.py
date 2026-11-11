"""Owner-only, presentation-only mobile Home enhancements. No DB writes."""
from flask import request
from markupsafe import Markup

_SCRIPT = r"""<script id="bm-owner-home-compact-v1">
(function(){
  if(window.__bmOwnerCompact) return;
  window.__bmOwnerCompact=true;
  function norm(s){return (s||'').replace(/\s+/g,' ').trim().toLocaleLowerCase('it');}
  function init(){
    if(!matchMedia('(max-width: 767px)').matches) return;
    var root=document.querySelector('main')||document.body;
    var headings=Array.from(root.querySelectorAll('h1,h2,h3,h4,h5,h6,.card-title,.section-title,strong,span,div,p')).filter(function(h){return h.children.length===0 && (norm(h.textContent).includes('certificato medico mancante') || norm(h.textContent).includes('mensilità da incassare'));});
    if(!headings.some(function(h){return norm(h.textContent).includes('certificato medico mancante');}) || !headings.some(function(h){return norm(h.textContent).includes('mensilità da incassare');}))return;
    function collapse(needle, id){
      var heading=headings.find(function(h){return norm(h.textContent).includes(needle) && h.getBoundingClientRect().width>0;});
      if(!heading) return;
      var block=heading.closest('section,article,.card,.panel,.dashboard-card,.widget,.alert-card,.home-card')||heading.parentElement;
      if(!block || block===root || block===document.body || block.querySelector('#'+id))return;
      var summary=document.createElement('button');
      summary.type='button';summary.id=id;
      summary.setAttribute('aria-expanded','false');
      summary.style.cssText='width:100%;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;background:transparent;border:0;color:inherit;font:inherit;text-align:left;cursor:pointer';
      var title=document.createElement('span');title.textContent=heading.textContent.trim();
      var arrow=document.createElement('span');arrow.textContent='⌄';arrow.setAttribute('aria-hidden','true');
      summary.append(title,arrow);
      var details=document.createElement('div');details.id=id+'-content';
      summary.setAttribute('aria-controls',details.id);
      if(heading.parentElement!==block){
        // Preserve unknown nested card markup by hiding only the card's existing siblings.
        var holder=heading.parentElement;
        if(holder===root || holder===document.body)return;
        Array.from(holder.children).forEach(function(child){if(child!==heading)details.appendChild(child);});
        heading.replaceWith(summary);
        holder.appendChild(details);
      }else{
        Array.from(block.children).forEach(function(child){if(child!==heading)details.appendChild(child);});
        heading.replaceWith(summary);
        block.appendChild(details);
      }
      details.hidden=true;
      summary.addEventListener('click',function(){details.hidden=!details.hidden;summary.setAttribute('aria-expanded',String(!details.hidden));arrow.textContent=details.hidden?'⌄':'⌃';});
    }
    collapse('certificato medico mancante','bm-owner-cert-toggle');
    collapse('mensilità da incassare','bm-owner-dues-toggle');
    if(!document.getElementById('bm-owner-bilanci-link')){
      var anchor=document.createElement('a');anchor.id='bm-owner-bilanci-link';
      anchor.href='/contabilita';
      anchor.style.cssText='display:flex;align-items:center;justify-content:space-between;gap:12px;margin:16px 0;padding:18px;border-radius:15px;background:#19364b;color:#f8f7f4;border:1px solid #68869b;text-decoration:none;font-weight:700';
      anchor.innerHTML='<span>▤ &nbsp; Bilanci <small style="display:block;font-weight:400;opacity:.85;margin-top:5px">Cassa · Banca · Entrate · Uscite</small></span><span aria-hidden="true">›</span>';
      root.appendChild(anchor);
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
</script>"""

def install(app):
    from asd_app.core import auth, has_role
    @app.after_request
    def owner_compact_home(response):
        if (request.method!='GET' or request.path.startswith('/app-tesserato/') or
            response.status_code!=200 or response.mimetype!='text/html' or
            response.direct_passthrough or not auth() or not has_role('admin')):
            return response
        page=response.get_data(as_text=True)
        if 'bm-owner-home-compact-v1' in page or '</body>' not in page.lower():
            return response
        page=page.replace('</body>',_SCRIPT+'</body>',1)
        response.set_data(page)
        response.headers.pop('ETag',None)
        response.headers['Cache-Control']='private, no-store'
        return response
