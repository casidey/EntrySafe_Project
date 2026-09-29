/* EntrySafe app shell: spring nav highlight, collapsible section panel, page filter, banners. */
(function () {
  'use strict';
  const { $, $$, reduce, Spring } = window.ES;
  const app = $('#app'); if (!app) return;

  const sideNav = $('#sideNav'), railNav = $('#railNav');
  const rail = $('#rail'), panel = $('#panel');
  const PANEL_W = 246;

  /* vertical highlight that slides between items -- also across full page loads (start where we were) */
  function makeVHi(nav, sel, key) {
    const y = new Spring(0), h = new Spring(0);
    const render = () => { const hi = $('.side-hi', nav); if (!hi) return; hi.style.transform = `translateY(${y.value}px)`; hi.style.height = h.value + 'px'; };
    function target() {
      const el = $$(sel, nav).find(b => b.getAttribute('aria-current') === 'true');
      if (!el || !nav.offsetParent) return null;
      const cr = nav.getBoundingClientRect(), br = el.getBoundingClientRect();
      return { y: br.top - cr.top, h: br.height };
    }
    function place(animate, from) {
      const t = target(); if (!t) return;
      if (from) { y.value = from.y; h.value = from.h; render(); }
      if (!animate || reduce) { y.value = t.y; y.vel = 0; h.value = t.h; h.vel = 0; render(); return; }
      y.to(t.y, { response: .42 }, render); h.to(t.h, { response: .42 }, render);
    }
    function remember() { try { sessionStorage.setItem(key, JSON.stringify({ y: y.value, h: h.value, t: Date.now() })); } catch (e) { /* ignore */ } }
    function restore() {
      try {
        const v = JSON.parse(sessionStorage.getItem(key) || 'null'); sessionStorage.removeItem(key);
        if (v && Date.now() - v.t < 6000) return v;
      } catch (e) { /* ignore */ }
      return null;
    }
    $$(sel, nav).forEach(a => a.addEventListener('click', remember));
    return { place, restore };
  }
  const side = makeVHi(sideNav, '.side-item', 'es-hi-side');
  const railHi = makeVHi(railNav, '.rail-item', 'es-hi-rail');
  function placeAll(animate) { side.place(animate); railHi.place(animate); }

  /* panel: spring-driven width; the icon rail appears only while the panel is collapsed */
  const panelW = new Spring(PANEL_W); let open = true;
  function paint(v) {
    const p = Math.min(1, Math.max(0, v / PANEL_W));
    panel.style.width = Math.max(0, v) + 'px'; panel.style.opacity = Math.min(1, v / 160);
    const rw = 56 * (1 - p);
    rail.style.width = rw + 'px'; rail.style.opacity = Math.min(1, rw / 40); rail.style.visibility = rw < 1 ? 'hidden' : 'visible';
  }
  function setOpen(next, animate) {
    open = next;
    try { localStorage.setItem('es-panel', open ? 'open' : 'closed'); } catch (e) { /* ignore */ }
    const to = open ? PANEL_W : 0;
    if (!animate || reduce) { panelW.value = to; panelW.vel = 0; paint(to); setTimeout(() => placeAll(false), 0); return; }
    panelW.to(to, { response: .45 }, paint, () => setTimeout(() => placeAll(false), 0));
    if (open) setTimeout(() => placeAll(false), 480);
  }
  $('#panelToggle').addEventListener('click', () => setOpen(!open, true));
  $('#railToggle').addEventListener('click', () => setOpen(!open, true));
  let stored = null; try { stored = localStorage.getItem('es-panel'); } catch (e) { /* ignore */ }
  if (stored === 'closed') setOpen(false, false);

  /* first paint: animate from the previous page's highlight position when we arrived by nav click */
  requestAnimationFrame(() => {
    const s = side.restore(), r = railHi.restore();
    if (s) side.place(true, s); else side.place(false);
    if (r) railHi.place(true, r); else railHi.place(false);
  });
  addEventListener('resize', () => placeAll(false));

  /* top search filters the rows on screen */
  const search = $('#topSearch');
  if (search) search.addEventListener('input', () => {
    const q = search.value.trim().toLowerCase();
    $$('.list-row', $('#content')).forEach(r => r.classList.toggle('filtered', !!q && !r.textContent.toLowerCase().includes(q)));
  });

  /* dismissible banner */
  $$('[data-bn="dismiss"]').forEach(btn => btn.addEventListener('click', () => {
    const b = btn.closest('.banner'); if (!b) return;
    b.classList.add('leaving'); setTimeout(() => b.remove(), reduce ? 0 : 480);
  }));

  /* entrance for page content */
  const content = $('#content');
  if (content && !reduce) {
    content.style.opacity = 0; content.style.transform = 'translateY(6px)';
    requestAnimationFrame(() => {
      content.style.transition = 'opacity .32s ease, transform .32s cubic-bezier(.22,1,.36,1)';
      content.style.opacity = 1; content.style.transform = 'none';
    });
  }

  /* server messages -> toast, then remove the static copy */
  $$('.flash .alert').forEach((el, i) => { if (i === 0) window.ES.toast(el.textContent.trim()); });
})();
