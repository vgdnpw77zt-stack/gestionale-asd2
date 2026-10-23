(function(){
 "use strict";
 const track=document.getElementById('familyMediaTrack');
 if(!track||track.dataset.bodymindLinksReady==='1')return;
 track.dataset.bodymindLinksReady='1';
 const urls={
   show:'https://www.instagram.com/reel/Ddle2ZbN086/?stkn=cHMxNzVwcHN1ZnV3',
   inside:'https://www.instagram.com/reel/DXEbNkAjT8K/?stkn=eDlzYzJsdHdoNWQ4',
   training:'https://www.instagram.com/reel/DOGdeS2Ddt1/?stkn=MWgyZHN2ajR1YjhlaA==',
   competition:'https://www.instagram.com/reel/DIHPtAbsg7B/?stkn=NHc5ejFsaWExd3Ri',
   site:'https://bodymindaerialstudio.life/#movimento'
 };
 function targetFor(title){
   const t=(title||'').toLocaleLowerCase('it');
   if(/gara|competition/.test(t))return urls.competition;
   if(/event|esibiz|spettacol|show/.test(t))return urls.show;
   if(/palestr|studio|dietro|quinte|intern/.test(t))return urls.inside;
   if(/allenament|training|lezion/.test(t))return urls.training;
   return urls.site;
 }
 for(const card of track.querySelectorAll('figure.media-card')){
   const image=card.querySelector(':scope > img');
   if(!image||image.closest('a'))continue;
   const caption=card.querySelector('figcaption strong');
   const title=caption?caption.textContent.trim():'Foto BodyMind';
   const a=document.createElement('a');
   a.className='bodymind-media-outbound';
   a.href=targetFor(title);
   a.target='_blank';a.rel='noopener noreferrer';a.referrerPolicy='no-referrer';
   a.setAttribute('aria-label','Apri sul sito il contenuto '+title);
   image.parentNode.insertBefore(a,image);a.appendChild(image);
   const badge=document.createElement('span');badge.className='bodymind-media-outbound-label';
   badge.textContent='Guarda ↗';a.appendChild(badge);
 }
})();