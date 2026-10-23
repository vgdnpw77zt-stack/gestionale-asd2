(function(){
"use strict";
function activate(){
const track=document.getElementById('familyMediaTrack');
if(!track||track.dataset.bodymindLinksReady==='1')return;
const u={
training:'https://www.instagram.com/reel/DOGdeS2Ddt1/?stkn=MWgyZHN2ajR1YjhlaA==',
competition:'https://www.instagram.com/reel/DIHPtAbsg7B/?stkn=NHc5ejFsaWExd3Ri',
show:'https://www.instagram.com/reel/Ddle2ZbN086/?stkn=cHMxNzVwcHN1ZnV3',
inside:'https://www.instagram.com/reel/DXEbNkAjT8K/?stkn=eDlzYzJsdHdoNWQ4',
site:'https://bodymindaerialstudio.life/#movimento'};
function hrefFor(label){
const t=(label||'').toLocaleLowerCase('it');
if(/gara|competition|campionat|podio/.test(t))return u.competition;
if(/event|esibiz|spettacol|show|saggio/.test(t))return u.show;
if(/palestr|studio|dietro|quinte|intern|bodymind/.test(t))return u.inside;
if(/allenament|training|lezion|corsi/.test(t))return u.training;
return u.site;
}
let modified=0;
for(const card of track.querySelectorAll('figure.media-card')){
if(card.querySelector('video,iframe,source,a.bodymind-media-outbound'))continue;
const photo=card.querySelector('img');
if(!photo)continue;
const title=card.querySelector('figcaption strong')?.textContent?.trim()||'Foto BodyMind';
const a=document.createElement('a');
a.className='bodymind-media-outbound';
a.href=hrefFor(title);
a.target='_blank';
a.rel='noopener noreferrer';
a.referrerPolicy='no-referrer';
a.setAttribute('aria-label','Guarda sul sito BodyMind: '+title);
card.appendChild(a);
modified++;
}
track.dataset.bodymindLinksReady='1';
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',activate,{once:true});else activate();
})();