(() => {
  const nav = document.querySelector('[data-nav]');
  const menuBtn = document.querySelector('[data-menu]');
  const mobileMenu = document.querySelector('[data-mobile-menu]');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const onScroll = () => {
    nav?.classList.toggle('scrolled', window.scrollY > 28);
    if (!reduced) {
      const media = document.querySelector('[data-parallax]');
      if (media) {
        const y = Math.min(window.scrollY * .11, 80);
        media.style.transform = 'translate3d(0,' + y + 'px,0) scale(1.02)';
      }
    }
  };
  onScroll();
  window.addEventListener('scroll', onScroll, {passive:true});

  if ('IntersectionObserver' in window && !reduced) {
    const io = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, {threshold:.14, rootMargin:'0px 0px -5% 0px'});
    document.querySelectorAll('.reveal').forEach(el => io.observe(el));
  } else {
    document.querySelectorAll('.reveal').forEach(el => el.classList.add('in'));
  }

  menuBtn?.addEventListener('click', () => {
    mobileMenu?.classList.toggle('open');
    menuBtn.textContent = mobileMenu?.classList.contains('open') ? 'Chiudi' : 'Menu';
  });
  mobileMenu?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    mobileMenu.classList.remove('open');
    if (menuBtn) menuBtn.textContent = 'Menu';
  }));

  const glow = document.querySelector('.cursor-glow');
  if (glow && matchMedia('(pointer:fine)').matches && !reduced) {
    window.addEventListener('pointermove', e => {
      glow.style.left = e.clientX + 'px';
      glow.style.top = e.clientY + 'px';
    }, {passive:true});
  }
})();
