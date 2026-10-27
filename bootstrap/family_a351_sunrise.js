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
    // No analytics, third-party uploads or cross-athlete galleries.
    // Existing family URLs already carry a private bearer token; never
    // construct a URL using an ID supplied by the browser.
    var match=location.pathname.match(/^\/app-tesserato\/([A-Za-z0-9_-]{12,180})\/?$/);
    if(match){
      var token=match[1];
      var ownBase="/app-tesserato/"+token+"/album";
      var section=document.querySelector("main.main .bm350-gallery-footer");
      if(section&&!section.querySelector(".bm351-private-album")){
        var albumLink=document.createElement("a");
        albumLink.className="bm350-gallery-more bm351-private-album";
        albumLink.href=ownBase;
        albumLink.textContent="Le mie foto · Crea il mio film";
        albumLink.setAttribute("aria-label","Apri il mio album privato e crea il mio film");
        albumLink.referrerPolicy="no-referrer";
        section.insertBefore(albumLink,section.firstChild);
      }
      var video=document.querySelector(".hero-media video.family-hero-video");
      if(video){
        fetch(ownBase+"/status",{credentials:"same-origin",cache:"no-store",redirect:"error"})
          .then(function(resp){if(!resp.ok)throw new Error("Album unavailable");return resp.json();})
          .then(function(data){
            if(!data||!data.available||typeof data.url!=="string")return;
            if(data.url!==ownBase+"/film")return;
            if(document.hidden)return;
            video.pause();
            video.querySelectorAll("source").forEach(function(s){s.remove();});
            video.src=data.url;
            video.preload="metadata";
            video.muted=true;
            video.load();
            var play=video.play();
            if(play&&typeof play.catch==="function")play.catch(function(){});
          })
          .catch(function(){/* Original academy film remains on any error. */});
      }
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
