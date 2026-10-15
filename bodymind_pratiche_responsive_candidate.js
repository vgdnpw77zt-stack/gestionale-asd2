/* BodyMind page-specific responsive opt-in. No data changes. */
(function () {
  if (!/^\/comunicazioni-automatiche(?:\/|$)/.test(location.pathname)) return;
  document.documentElement.classList.add('bodymind-pratiche-responsive-root');
  document.addEventListener('DOMContentLoaded', function () {
    document.body.classList.add('bodymind-pratiche-responsive');
  }, { once: true });
})();
