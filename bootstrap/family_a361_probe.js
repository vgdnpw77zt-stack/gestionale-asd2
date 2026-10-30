/* A361 - anonymous home layout diagnostics, no page text or personal data. */
(function(){"use strict";
if(!location.pathname.startsWith("/app-tesserato/"))return;
function rounded(n){return Number.isFinite(n)?Math.round(n):0}
function summary(el){
 if(!el)return {found:false};
 var r=el.getBoundingClientRect(),s=getComputedStyle(el);
 return {found:true,tag:el.tagName.toLowerCase(),position:s.position,display:s.display,
 width:rounded(r.width),height:rounded(r.height),top:rounded(r.top),left:rounded(r.left),
 z:s.zIndex,opacity:s.opacity,overflow:s.overflow,
 bgTransparent:(s.backgroundColor==="rgba(0, 0, 0, 0)"||s.backgroundColor==="transparent")};
}
function run(){
 try{
 var hero=document.querySelector(".hero"),
 intro=document.querySelector(".hero .hero-intro"),
 video=document.querySelector(".hero .hero-media video,.hero video"),
 sky=document.querySelector("main.main>.bm352-sky"),
 link=document.getElementById("bodymind-a360-style");
 var h=hero&&getComputedStyle(hero,"::before");
 var sh=sky&&getComputedStyle(sky,"::after");
 var report={family:true,inner:rounded(innerWidth),doc:rounded(document.documentElement.clientWidth),
 mobile:matchMedia("(max-width:760px)").matches,
 viewport:!!document.querySelector('meta[name="viewport"]'),
 hero:summary(hero),content:summary(document.querySelector(".hero .hero-content")),
 intro:summary(intro),video:summary(video),
 sky:summary(sky),
 beforeAnimation:h?h.animationName:"none",beforeContent:h?h.content:"missing",
 skyAnimation:sh?sh.animationName:"none",
 stylePresent:!!link,styleLoaded:!!(link&&link.sheet),
 styles:Array.from(document.styleSheets).length};
 fetch("/_bodymind_a361_probe",{method:"POST",headers:{"Content-Type":"application/json"},
  credentials:"same-origin",keepalive:true,body:JSON.stringify(report)}).catch(function(){});
 }catch(e){}
}
if(document.readyState==="complete")requestAnimationFrame(function(){setTimeout(run,400)});
else addEventListener("load",function(){requestAnimationFrame(function(){setTimeout(run,400)})},{once:true});
})();