/* BodyMind A350: explicit media permissions; no title-based guessing.
   The authoritative business values and user session remain server-owned. */
(function () {
  "use strict";
  // Approved association observed in the official BodyMind site's
  // curated competition media slot. Unknown photos deliberately stay unlinked.
  const verifiedImageLinks = Object.freeze({
    "/static/media/bodymind-competition-double.webp": "https://www.instagram.com/reel/DIHPtAbsg7B/"
  });
  const officialGallery = "https://bodymindaerialstudio.life/#movimento";
  function publicPath(img) {
    try {
      const source = img.getAttribute("src");
      if (!source) return "";
      const url = new URL(source, document.baseURI);
      // Compare the displayed asset, not a potentially different srcset fallback.
      // With srcset/picture, wait for currentSrc before associating a reel.
      if ((img.hasAttribute("srcset") || img.closest("picture")) && !img.currentSrc) return "";
      const shown = new URL(img.currentSrc || url.href, document.baseURI);
      // Public official site hosts are explicitly trusted; every other origin fails closed.
      const official = new Set([
        window.location.origin,
        "https://bodymindaerialstudio.life",
        "https://www.bodymindaerialstudio.life"
      ]);
      if (shown.protocol !== "https:" && shown.origin !== window.location.origin) return "";
      if (!official.has(shown.origin)) return "";
      if (shown.search || shown.hash) return "";
      return shown.pathname;
    } catch (_) {
      return "";
    }
  }
  function prepareGallery() {
    const track = document.getElementById("familyMediaTrack");
    if (!track || track.dataset.bm350Ready === "1") return;
    track.dataset.bm350Ready = "1";
    for (const card of track.querySelectorAll("figure.media-card")) {
      const img = card.querySelector(":scope > img");
      if (!img || img.closest("a")) continue;
      const title = card.querySelector("figcaption strong");
      const name = title ? title.textContent.trim() : "BodyMind";
      if (!img.hasAttribute("alt") || !img.alt.trim()) img.alt = name;
      img.loading = "lazy";
      img.decoding = "async";
      img.addEventListener("error", function () {
        if (img.dataset.bm350Failed === "1") return;
        img.dataset.bm350Failed = "1";
        const placeholder = document.createElement("span");
        placeholder.className = "bm350-media-unavailable";
        placeholder.textContent = "Immagine non disponibile";
        img.replaceWith(placeholder);
      }, {once:true});
      const destination = verifiedImageLinks[publicPath(img)];
      if (!destination) continue;
      const link = document.createElement("a");
      link.className = "bm350-media-link";
      link.href = destination;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.referrerPolicy = "no-referrer";
      link.setAttribute("aria-label", "Guarda il contenuto ufficiale: " + name);
      img.parentNode.insertBefore(link, img);
      link.appendChild(img);
      const cue = document.createElement("span");
      cue.className = "bm350-media-link-label";
      cue.textContent = "Guarda";
      link.appendChild(cue);
    }
    if (!track.parentElement || track.parentElement.querySelector(".bm350-gallery-footer")) return;
    const footer = document.createElement("div");
    footer.className = "bm350-gallery-footer";
    const link = document.createElement("a");
    link.className = "bm350-gallery-more";
    link.href = officialGallery;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.referrerPolicy = "no-referrer";
    link.textContent = "Scopri BodyMind in movimento";
    footer.appendChild(link);
    track.insertAdjacentElement("afterend", footer);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", prepareGallery, {once:true});
  } else {
    prepareGallery();
  }
})();
