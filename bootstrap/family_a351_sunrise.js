/* BodyMind A351 Sunrise: navigation only, privacy-neutral. */
(function(){
  "use strict";
  function init(){
    var area=document.querySelector("main.main");
    if(area&&!area.querySelector(".bm351-atmosphere")){
      var atmosphere=document.createElement("div");
      atmosphere.className="bm351-atmosphere";
      atmosphere.setAttribute("aria-hidden","true");
      area.insertBefore(atmosphere,area.firstChild);
    }
    var nav=document.querySelector(".bottom-nav");
    if(!nav||nav.querySelector(".bm351-dock-toggle"))return;
    if(!nav.querySelector("a"))return;
    var button=document.createElement("button");
    button.type="button";
    button.className="bm351-dock-toggle";
    button.textContent="Riduci menu";
    button.setAttribute("aria-label","Riduci menu di navigazione");
    button.setAttribute("aria-expanded","true");
    var mobile=window.matchMedia("(max-width: 760px)");
    var collapsed=false;
    function setCollapsed(value){
      collapsed=!!value&&mobile.matches;
      nav.classList.toggle("bm351-collapsed",collapsed);
      button.textContent=collapsed?"Apri menu":"Riduci menu";
      button.setAttribute("aria-label",collapsed?"Apri menu di navigazione":"Riduci menu di navigazione");
      button.setAttribute("aria-expanded",collapsed?"false":"true");
    }
    button.addEventListener("click",function(){setCollapsed(!collapsed);});
    nav.appendChild(button);
    nav.addEventListener("focusin",function(e){if(e.target!==button)setCollapsed(false);});
    nav.querySelectorAll("a").forEach(function(link){
      link.addEventListener("click",function(){if(mobile.matches)setCollapsed(true);});
    });
    var lastScroll=window.scrollY;
    var rafPending=false;
    window.addEventListener("scroll",function(){
      if(rafPending||!mobile.matches)return;
      rafPending=true;
      requestAnimationFrame(function(){
        rafPending=false;
        var y=window.scrollY,delta=y-lastScroll;
        if(Math.abs(delta)>19){
          if(y>220&&delta>0&&!nav.contains(document.activeElement))setCollapsed(true);
          if(delta<0)setCollapsed(false);
          lastScroll=y;
        }
      });
    },{passive:true});
    if(typeof mobile.addEventListener==="function"){
      mobile.addEventListener("change",function(){setCollapsed(false);});
    }
    setCollapsed(false);
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});
  else init();
})();
