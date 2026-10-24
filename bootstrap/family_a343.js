(function(){
'use strict';
function init(){
const track=document.getElementById('familyMediaTrack');
const area=document.querySelector('.media-carousel');
if(!track||!area||track.dataset.bmAutoCarousel==='1')return;
track.dataset.bmAutoCarousel='1';
const section=document.getElementById('media');
const reduced=!!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches);
const saveData=!!(navigator.connection&&navigator.connection.saveData);
const cards=Array.from(track.querySelectorAll('.media-card'));
if(cards.length<2)return;
const controls=section&&section.querySelector('.media-controls');
const toggle=document.createElement('button');
toggle.type='button';toggle.className='bm-carousel-toggle';
toggle.setAttribute('aria-label','Metti in pausa o riprendi lo scorrimento automatico del carosello');
if(controls)controls.appendChild(toggle);
let userPaused=reduced||saveData,inView=true,userInteracting=false,resumeAt=0;
let lastAdvance=Date.now(),scrollWaitUntil=0,activeVideo=null,videoStart=0;
function paused(){return userPaused||userInteracting||!inView||document.hidden;}
function updateControl(){toggle.setAttribute('aria-pressed',userPaused?'true':'false');toggle.textContent=userPaused?'▶ Riprendi':'Ⅱ Pausa';area.dataset.autoplayActive=paused()?'false':'true';}
function pauseVideos(except){
for(const v of track.querySelectorAll('video'))if(v!==except&&!v.paused){try{v.pause();}catch(_){}}
}
function selectVideo(){
if(paused()||Date.now()<resumeAt){pauseVideos(null);activeVideo=null;return;}
const rect=track.getBoundingClientRect();let best=null,bestRatio=0;
for(const card of cards){
const video=card.querySelector('video');if(!video)continue;
const box=card.getBoundingClientRect();
const visible=Math.max(0,Math.min(rect.right,box.right)-Math.max(rect.left,box.left));
const ratio=visible/Math.max(1,box.width);
if(ratio>bestRatio){best=video;bestRatio=ratio;}
}
if(bestRatio<.77){pauseVideos(null);activeVideo=null;return;}
best.muted=true;best.defaultMuted=true;best.playsInline=true;
best.setAttribute('playsinline','');best.loop=true;
if(best!==activeVideo){activeVideo=best;videoStart=Date.now();lastAdvance=Date.now();}
pauseVideos(best);
if(best.paused){const promise=best.play();if(promise&&promise.catch)promise.catch(()=>{});}
}
function advance(){
if(paused())return;
if(activeVideo&&!activeVideo.paused&&Date.now()-videoStart<11500)return;
const max=Math.max(0,track.scrollWidth-track.clientWidth);
if(max<12)return;
const nextCard=cards.find(c=>c.offsetLeft-track.offsetLeft>track.scrollLeft+16);
const next=nextCard?Math.min(max,nextCard.offsetLeft-track.offsetLeft):0;
pauseVideos(null);activeVideo=null;
track.scrollTo({left:next,behavior:reduced?'auto':'smooth'});
lastAdvance=Date.now();scrollWaitUntil=Date.now()+1100;
}
toggle.addEventListener('click',()=>{
userPaused=!userPaused;userInteracting=false;resumeAt=0;lastAdvance=Date.now();
updateControl();if(userPaused)pauseVideos(null);else selectVideo();
});
function manualPause(){userInteracting=true;resumeAt=Date.now()+14000;lastAdvance=Date.now();pauseVideos(null);updateControl();}
track.addEventListener('pointerdown',manualPause,{passive:true});
track.addEventListener('keydown',manualPause);
track.addEventListener('wheel',manualPause,{passive:true});
for(const id of ['familyPrev','familyNext'])document.getElementById(id)?.addEventListener('click',manualPause);
if('IntersectionObserver' in window){
new IntersectionObserver(entries=>{
inView=entries.some(e=>e.isIntersecting&&e.intersectionRatio>=.25);
if(!inView)pauseVideos(null);
updateControl();
},{threshold:[0,.25,.6]}).observe(area);
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseVideos(null);updateControl();});
track.addEventListener('scroll',()=>{if(Date.now()>scrollWaitUntil)activeVideo=null;},{passive:true});
window.setInterval(()=>{
if(userInteracting&&Date.now()>resumeAt)userInteracting=false;
if(paused()){pauseVideos(null);updateControl();return;}
selectVideo();if(Date.now()-lastAdvance>=6500)advance();updateControl();
},1000);
updateControl();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();