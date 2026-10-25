(function(){
  "use strict";
  var media=document.querySelector(".hero-media");
  var button=document.querySelector(".hero-playback");
  if(!media||!button)return;
  var original=button.parentNode;
  var marker=document.createComment("A345 playback original position");
  original.insertBefore(marker,button);
  var mq=window.matchMedia("(max-width:760px)");
  function layout(){
    if(mq.matches){
      if(button.parentNode!==media)media.appendChild(button);
    }else if(marker.parentNode&&button.parentNode!==original){
      marker.parentNode.insertBefore(button,marker);
    }
  }
  layout();
  if(typeof mq.addEventListener==="function")mq.addEventListener("change",layout);
  else if(typeof mq.addListener==="function")mq.addListener(layout);
})();