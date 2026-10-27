/* BODYMIND A353: visual-only nebula augmentation.
   No storage, fetch, cookies, session data or changes to business actions. */
(function(){
  "use strict";
  function addVapor(host){
    if(!host)return;
    var sky=host.querySelector(":scope > .bm352-sky");
    if(!sky||sky.querySelector(".bm353-vapor"))return;
    var classes=["bm353-vapor bm353-vapor--aqua","bm353-vapor bm353-vapor--peach",
      "bm353-vapor bm353-vapor--veils","bm353-vapor bm353-vapor--aura"];
    var stars=sky.querySelector(".bm352-dust");
    classes.forEach(function(name){
      var cloud=document.createElement("span");
      cloud.className=name;
      cloud.setAttribute("aria-hidden","true");
      if(stars)sky.insertBefore(cloud,stars);
      else sky.appendChild(cloud);
    });
  }
  function init(){
    if(document.documentElement.classList.contains("bm353-ready"))return;
    var hero=document.querySelector("section.hero");
    var main=document.querySelector("main.main");
    if(!hero&&!main)return;
    document.documentElement.classList.add("bm353-ready");
    addVapor(hero);
    addVapor(main);
    /* Preserve the video source and controls; guarantee iPhone inline playback
       without accidentally switching on audible autoplay. */
    var movie=hero&&hero.querySelector("video.family-hero-video, video#familyHeroVideo");
    if(movie){
      movie.playsInline=true;
      movie.setAttribute("playsinline","");
      if(movie.autoplay)movie.muted=true;
    }
  }
  if(document.readyState==="loading")
    document.addEventListener("DOMContentLoaded",init,{once:true});
  else init();
})();
