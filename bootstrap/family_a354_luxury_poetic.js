/* BODYMIND A354 Luxury Poetic — scenery only. No uploads, requests, or user data. */
(function(){
  "use strict";
  var SVG="http://www.w3.org/2000/svg";
  function silhouette(kind){
    var art=document.createElementNS(SVG,"svg");
    art.setAttribute("viewBox","0 0 180 200");
    art.setAttribute("class","bm354-hoop bm354-hoop--"+kind);
    art.setAttribute("focusable","false");
    art.setAttribute("aria-hidden","true");
    var ring=document.createElementNS(SVG,"ellipse");
    ring.setAttribute("cx","91");ring.setAttribute("cy","98");
    ring.setAttribute("rx","64");ring.setAttribute("ry","71");
    ring.setAttribute("fill","none");
    ring.setAttribute("stroke","#d5fff0");ring.setAttribute("stroke-width","2.2");
    art.appendChild(ring);
    var ribbon=document.createElementNS(SVG,"path");
    ribbon.setAttribute("d","M91 0 L91 28 M90 171 L90 196");
    ribbon.setAttribute("stroke","#c2ecec");
    ribbon.setAttribute("stroke-width","1.2");
    ribbon.setAttribute("stroke-linecap","round");
    ribbon.setAttribute("fill","none");
    art.appendChild(ribbon);
    var dancer=document.createElementNS(SVG,"path");
    dancer.setAttribute("d","M99 69 C108 70 112 80 106 87 C101 92 92 89 90 81 C88 75 92 69 99 69 Z M97 91 C88 102 86 119 91 132 C95 145 111 149 119 158 C126 163 133 164 141 159 M93 113 C81 107 67 97 55 90 M91 122 C79 132 72 146 72 164 C71 170 69 176 65 181 M102 101 C116 96 124 88 131 75");
    dancer.setAttribute("stroke","#f5d8cc");
    dancer.setAttribute("stroke-width","3.1");
    dancer.setAttribute("stroke-linecap","round");
    dancer.setAttribute("stroke-linejoin","round");
    dancer.setAttribute("fill","none");
    art.appendChild(dancer);
    return art;
  }
  function layer(host,kind){
    if(!host)return;
    var sky=host.querySelector(":scope > .bm352-sky");
    if(!sky||sky.querySelector(".bm354-silk"))return;
    ["bm354-silk","bm354-silk bm354-silk--second",
     "bm354-silk bm354-silk--third","bm354-star-glimmer"].forEach(function(name){
      var el=document.createElement("span");
      el.className=name;
      el.setAttribute("aria-hidden","true");
      sky.appendChild(el);
    });
    sky.appendChild(silhouette(kind));
  }
  function init(){
    if(document.documentElement.classList.contains("bm354-ready"))return;
    var hero=document.querySelector("section.hero"),main=document.querySelector("main.main");
    if(!hero&&!main)return;
    document.documentElement.classList.add("bm354-ready");
    layer(hero,"hero");
    layer(main,"main");
  }
  if(document.readyState==="loading"){
    document.addEventListener("DOMContentLoaded",init,{once:true});
  }else init();
})();
