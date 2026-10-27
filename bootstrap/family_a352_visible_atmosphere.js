/* BODYMIND A352: visible cinematic sky + genuinely sliding footer.
   No network, cookies, storage, accounting or private data access. */
(function(){
  "use strict";
  function buildSky(host){
    if(!host||host.querySelector(':scope > .bm352-sky'))return;
    var sky=document.createElement("div");
    sky.className="bm352-sky";
    sky.setAttribute("aria-hidden","true");
    ["bm352-cloud bm352-cloud--far","bm352-cloud bm352-cloud--near",
      "bm352-dust","bm352-dust bm352-dust--far"].forEach(function(cls){
      var layer=document.createElement("span");
      layer.className=cls;
      sky.appendChild(layer);
    });
    host.insertBefore(sky,host.firstChild);
  }
  function initialize(){
    if(document.documentElement.classList.contains("bm352-initialized"))return;
    document.documentElement.classList.add("bm352-initialized");
    buildSky(document.querySelector("section.hero"));
    buildSky(document.querySelector("main.main"));

    var hero=document.querySelector(".hero .hero-media");
    if(hero&&!hero.querySelector(".bm352-glow")){
      var glow=document.createElement("div");
      glow.className="bm352-glow";
      glow.setAttribute("aria-hidden","true");
      hero.insertBefore(glow,hero.firstChild);
    }

    var dock=document.querySelector("nav.bottom-nav");
    if(!dock||!dock.querySelector("a"))return;
    dock.classList.add("bm352-dock");
    var legacyToggle=dock.querySelector(".bm351-dock-toggle");
    if(legacyToggle)legacyToggle.hidden=true;
    var handle=document.createElement("button");
    handle.type="button";
    handle.className="bm352-dock-handle";
    handle.setAttribute("aria-controls","bm352-navigation");
    handle.setAttribute("aria-label","Mostra o nascondi il menu BodyMind");
    if(!dock.id)dock.id="bm352-navigation";
    handle.setAttribute("aria-controls",dock.id);
    document.body.appendChild(handle);
    var mobile=window.matchMedia("(max-width:760px)");
    var isOpen=true;
    var lastY=window.scrollY;
    var ticking=false;

    function setOpen(open){
      isOpen=!mobile.matches||!!open;
      dock.classList.remove("bm351-collapsed");
      dock.classList.toggle("bm352-tucked",!isOpen);
      dock.setAttribute("aria-hidden",isOpen?"false":"true");
      handle.setAttribute("aria-expanded",isOpen?"true":"false");
      handle.textContent=isOpen?"Nascondi menu":"Apri menu";
      dock.querySelectorAll("a").forEach(function(link){
        if(!isOpen)link.setAttribute("tabindex","-1");
        else link.removeAttribute("tabindex");
      });
    }
    function updateDockHeight(){
      if(!mobile.matches)return;
      var height=dock.getBoundingClientRect().height;
      if(height>25&&height<280){
        document.documentElement.style.setProperty("--bm352-dock-height",Math.round(height)+"px");
      }
    }
    handle.addEventListener("click",function(){
      setOpen(!isOpen);
      updateDockHeight();
    });
    document.addEventListener("keydown",function(ev){
      if(ev.key==="Escape"&&mobile.matches&&isOpen){
        setOpen(false);
        handle.focus();
      }
    });
    dock.addEventListener("focusin",function(){setOpen(true);});
    function scrolled(){
      ticking=false;
      if(!mobile.matches)return;
      var current=Math.max(0,window.scrollY);
      var diff=current-lastY;
      if(Math.abs(diff)>10){
        // Scrolling down tucks entire bar; scrolling up reveals it.
        if(diff>0&&current>180&&!dock.contains(document.activeElement))setOpen(false);
        if(diff<0)setOpen(true);
        lastY=current;
      }
    }
    window.addEventListener("scroll",function(){
      if(!ticking){
        ticking=true;
        window.requestAnimationFrame(scrolled);
      }
    },{passive:true});
    function resized(){
      setOpen(true);
      updateDockHeight();
    }
    if(typeof mobile.addEventListener==="function")mobile.addEventListener("change",resized);
    window.addEventListener("resize",updateDockHeight,{passive:true});
    window.addEventListener("pageshow",resized);
    setOpen(true);
    updateDockHeight();
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",initialize,{once:true});
  else initialize();
})();
