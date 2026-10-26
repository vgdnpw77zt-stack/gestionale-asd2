/* BodyMind A349: keep the full original video proportions once known.
   No network, user data, DOM replacement or playback changes. */
(function () {
  "use strict";
  function keepNativeRatio(video) {
    var width = Number(video.videoWidth);
    var height = Number(video.videoHeight);
    if (!(width > 0 && height > 0)) return;
    if (width > 10000 || height > 10000) return;
    video.style.setProperty("--bm349-film-ratio", width + " / " + height);
  }
  function prepare() {
    var video = document.querySelector(".hero-media video.family-hero-video");
    if (!video) return;
    keepNativeRatio(video);
    video.addEventListener("loadedmetadata", function () {
      keepNativeRatio(video);
    }, {passive: true});
    video.addEventListener("resize", function () {
      keepNativeRatio(video);
    }, {passive: true});
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", prepare, {once: true});
  } else {
    prepare();
  }
})();