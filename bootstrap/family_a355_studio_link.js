/* A355 studio entry — links only; preserves existing navigation and data. */
(function(){
  "use strict";
  function init(){
    if(document.querySelector(".bm355-film-card"))return;
    var m=location.pathname.match(/^\/app-tesserato\/([A-Za-z0-9_-]{12,180})(?:\/|$)/);
    if(!m)return;
    var main=document.querySelector("main.main");
    if(!main)return;
    var card=document.createElement("section");
    card.className="bm355-film-card";
    var copy=document.createElement("div");
    var title=document.createElement("strong");title.textContent="I miei momenti in volo";
    var info=document.createElement("p");
    info.textContent="Le tue foto, una colonna sonora e un film tutto tuo da conservare.";
    copy.appendChild(title);copy.appendChild(info);
    var link=document.createElement("a");
    link.href="/app-tesserato/"+encodeURIComponent(m[1])+"/studio";
    link.textContent="Crea il mio film";
    card.appendChild(copy);card.appendChild(link);
    var first=main.querySelector(".stats,.section");
    if(first)main.insertBefore(card,first);
    else main.appendChild(card);
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});
  else init();
})();
