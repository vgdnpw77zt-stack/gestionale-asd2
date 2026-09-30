(()=>{const nav=document.querySelector("[data-nav]"),menu=document.querySelector("[data-menu]"),mobile=document.querySelector("[data-mobile-menu]"),reduced=matchMedia("(prefers-reduced-motion: reduce)").matches;function onScroll(){nav?.classList.toggle("scrolled",scrollY>22)}onScroll();addEventListener("scroll",onScroll,{passive:true});menu?.addEventListener("click",()=>{const open=mobile?.classList.toggle("open");menu.setAttribute("aria-expanded",open?"true":"false");menu.textContent=open?"Chiudi":"Menu"});mobile?.querySelectorAll("a").forEach(a=>a.addEventListener("click",()=>{mobile.classList.remove("open");menu?.setAttribute("aria-expanded","false");if(menu)menu.textContent="Menu"}));if("IntersectionObserver" in window&&!reduced){const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add("in");io.unobserve(e.target)}}),{threshold:.1,rootMargin:"0px 0px -4% 0px"});document.querySelectorAll(".reveal").forEach(x=>io.observe(x))}else{document.querySelectorAll(".reveal").forEach(x=>x.classList.add("in"))}const v=document.querySelector("[data-hero-video]"),p=document.querySelector("[data-native-play]");if(v){v.muted=true;v.playsInline=true;const play=()=>v.play().then(()=>{if(p)p.hidden=true}).catch(()=>{if(p)p.hidden=false});play();document.addEventListener("visibilitychange",()=>{if(!document.hidden)play()});p?.addEventListener("click",play)};const kv=document.querySelector("[data-kids-video]"),ks=document.querySelector("[data-kids-video-shell]");if(kv){kv.muted=true;kv.playsInline=true;let visible=false;const sync=()=>{if(document.hidden||!visible||reduced){kv.pause();ks?.classList.remove("is-playing");return}kv.play().then(()=>ks?.classList.add("is-playing")).catch(()=>ks?.classList.remove("is-playing"))};if("IntersectionObserver"in window){const kio=new IntersectionObserver(es=>es.forEach(e=>{visible=e.isIntersecting&&e.intersectionRatio>=.28;sync()}),{threshold:[0,.28,.55],rootMargin:"0px 0px -4% 0px"});kio.observe(kv)}else{visible=true;sync()}document.addEventListener("visibilitychange",sync)}const dock=document.querySelector(".mobile-action-dock");let dockScrollTimer;const fadeDockOnScroll=()=>{if(!dock)return;dock.classList.add("is-scrolling");clearTimeout(dockScrollTimer);dockScrollTimer=setTimeout(()=>dock.classList.remove("is-scrolling"),420)};addEventListener("scroll",fadeDockOnScroll,{passive:true});dock?.addEventListener("touchstart",()=>dock.classList.remove("is-scrolling"),{passive:true});
const analyticsSession=String(window.BODYMIND_ANALYTICS_SESSION||"");
if(analyticsSession){
  const started=Date.now();
  let maxScroll=0,ended=false;
  const seenSections=new Set();
  const send=(event,label="",meta={},beacon=false)=>{
    const payload={session_id:analyticsSession,event,label,duration_ms:Math.max(0,Date.now()-started),scroll_pct:maxScroll,meta};
    const raw=JSON.stringify(payload);
    if(beacon&&navigator.sendBeacon){
      try{navigator.sendBeacon("/analytics/event",new Blob([raw],{type:"application/json"}));return}catch(e){}
    }
    try{fetch("/analytics/event",{method:"POST",headers:{"Content-Type":"application/json"},body:raw,keepalive:true,credentials:"same-origin"})}catch(e){}
  };
  const updateScroll=()=>{
    const root=document.documentElement;
    const total=Math.max(1,root.scrollHeight-innerHeight);
    maxScroll=Math.max(maxScroll,Math.min(100,Math.round((scrollY/total)*100)));
  };
  addEventListener("scroll",updateScroll,{passive:true});
  updateScroll();

  const sections=["percorsi","kids","movimento","sedi","contatti"];
  if("IntersectionObserver" in window){
    const sio=new IntersectionObserver(entries=>entries.forEach(e=>{
      if(e.isIntersecting&&e.intersectionRatio>=.35&&!seenSections.has(e.target.id)){
        seenSections.add(e.target.id);send("section_view",e.target.id);
      }
    }),{threshold:[.35,.6]});
    sections.forEach(id=>{const el=document.getElementById(id);if(el)sio.observe(el)});
  }

  document.addEventListener("click",ev=>{
    const a=ev.target.closest("a");
    if(!a)return;
    const href=String(a.getAttribute("href")||"");
    const absolute=String(a.href||href);
    const text=String(a.textContent||"").trim().replace(/\s+/g," ").slice(0,120);
    let event="";
    if(/wa\.me\//i.test(absolute))event="whatsapp_click";
    else if(/^tel:/i.test(href))event="phone_click";
    else if(/^mailto:/i.test(href))event="email_click";
    else if(/google\.com\/maps/i.test(absolute))event="map_click";
    else if(/area-famiglie/i.test(absolute))event="family_click";
    else if(/instagram\.com\/(reel|p)\//i.test(absolute))event="reel_click";
    else if(/instagram\.com/i.test(absolute))event="instagram_click";
    else if(href==="#contatti"||a.classList.contains("primary-btn")||a.classList.contains("header-cta")||a.classList.contains("primary"))event="cta_click";
    if(event)send(event,text,{href:absolute.slice(0,300)});
  },{capture:true});

  const endSession=()=>{
    if(ended)return;ended=true;updateScroll();send("session_end","",{},true);
  };
  addEventListener("pagehide",endSession,{capture:true});
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="hidden")endSession()});
}
})();