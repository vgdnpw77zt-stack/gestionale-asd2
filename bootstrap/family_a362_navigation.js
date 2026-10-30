(()=>{'use strict';
const nav=document.querySelector('.bottom-nav');if(!nav)return;
nav.id='bm362-dock';
const toggle=document.createElement('button');toggle.type='button';toggle.className='bm362-menu';toggle.setAttribute('aria-controls',nav.id);toggle.setAttribute('aria-label','Mostra o nascondi il menu BodyMind');document.body.appendChild(toggle);
function setOpen(open){nav.classList.toggle('bm362-closed',!open);nav.inert=!open;toggle.setAttribute('aria-expanded',String(open));toggle.textContent=open?'Nascondi menu ↓':'Menu ↑'}
toggle.addEventListener('click',()=>setOpen(toggle.getAttribute('aria-expanded')!=='true'));
nav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{if(matchMedia('(max-width:760px)').matches)setOpen(false)}));
let last=scrollY,pending=false;addEventListener('scroll',()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{if(scrollY>last+8 && !nav.contains(document.activeElement))setOpen(false);last=scrollY;pending=false})},{passive:true});
setOpen(false);
const footer=document.querySelector('.bm350-gallery-footer');
const studio=document.querySelector('.bm362-studio a');
if(footer&&studio){const a=document.createElement('a');a.href=studio.getAttribute('href').replace(/\/studio$/,'/album');a.className='bm350-gallery-more bm351-private-album';a.textContent='Il mio album privato';footer.prepend(a)}
})();
