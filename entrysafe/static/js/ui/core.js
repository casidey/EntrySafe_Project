/* EntrySafe UI core: spring engine, sliding chip groups, toast, confirm modal, theme. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* critically-damped spring, interruptible (semi-implicit Euler) */
  function Spring(value) { this.value = value; this.vel = 0; this.target = value; this._raf = null; }
  Spring.prototype.to = function (target, opts, onUpdate, onDone) {
    const response = (opts && opts.response) || .4;
    const damping = (opts && opts.damping) != null ? opts.damping : 1;
    this.target = target;
    if (reduce) { this.value = target; this.vel = 0; onUpdate(this.value); if (onDone) onDone(); return; }
    if (this._raf) cancelAnimationFrame(this._raf);
    const k = Math.pow(2 * Math.PI / response, 2), c = 2 * Math.sqrt(k) * damping;
    let last = performance.now();
    const step = (now) => {
      const dt = Math.min(.032, (now - last) / 1000); last = now;
      const accel = -k * (this.value - this.target) - c * this.vel;
      this.vel += accel * dt; this.value += this.vel * dt; onUpdate(this.value);
      if (Math.abs(this.value - this.target) < .0008 && Math.abs(this.vel) < .0008) {
        this.value = this.target; onUpdate(this.value); this._raf = null; if (onDone) onDone(); return;
      }
      this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
  };

  /* toast */
  let toastTimer = 0;
  function toast(msg) {
    const el = $('#toast'); if (!el) return;
    el.textContent = msg; el.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
  }

  /* generic confirm modal (needs #scrim2 / #modal2 from the shell) */
  function confirmModal(opts) {
    const scrim = $('#scrim2'), modal = $('#modal2'); if (!scrim || !modal) { if (opts.onConfirm) opts.onConfirm(); return; }
    $('#modal2Title').textContent = opts.title; $('#modal2Sub').textContent = opts.sub || '';
    $('#modal2Confirm').textContent = opts.action || 'Confirm';
    const icon = $('#modal2Icon'); icon.classList.toggle('warn', !!opts.warn);
    icon.innerHTML = opts.warn ? '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>'
                               : '<svg viewBox="0 0 24 24"><path d="M5 13l4 4 10-10"/></svg>';
    const reason = $('#modal2Reason');
    if (reason) { reason.hidden = !opts.reason; reason.value = ''; reason.placeholder = opts.reason || ''; }
    scrim.classList.add('show'); modal.classList.add('show');
    const ok = $('#modal2Confirm'), cancel = $('#modal2Cancel');
    const close = (yes) => {
      scrim.classList.remove('show'); modal.classList.remove('show');
      ok.removeEventListener('click', onOk); cancel.removeEventListener('click', onNo);
      scrim.removeEventListener('click', onNo); document.removeEventListener('keydown', onKey);
      if (yes && opts.onConfirm) opts.onConfirm(reason && !reason.hidden ? reason.value.trim() : '');
    };
    const onOk = () => close(true), onNo = () => close(false), onKey = (e) => { if (e.key === 'Escape') close(false); };
    ok.addEventListener('click', onOk); cancel.addEventListener('click', onNo);
    scrim.addEventListener('click', onNo); document.addEventListener('keydown', onKey);
    ok.focus();
  }

  /* forms that ask before submitting: <form data-confirm-title="..." data-confirm-sub="..." data-confirm-action="..." data-confirm-warn> */
  document.addEventListener('submit', (e) => {
    const f = e.target; if (!f.matches || !f.matches('form[data-confirm-title]') || f._confirmed) return;
    e.preventDefault();
    confirmModal({
      title: f.dataset.confirmTitle, sub: f.dataset.confirmSub, action: f.dataset.confirmAction,
      warn: f.hasAttribute('data-confirm-warn'), reason: f.dataset.confirmReason,
      onConfirm: (text) => { const r = f.querySelector('input[name=reason]'); if (r) r.value = text; f._confirmed = true; f.submit(); }
    });
  });

  /* sliding chip group backed by a hidden input: <div class="chips" data-input="id"> */
  function makeChips(root, onChange) {
    const btns = $$('button', root), hi = $('.chip-hi', root);
    const xs = new Spring(0), ws = new Spring(0);
    const render = () => { hi.style.transform = `translateX(${xs.value}px)`; hi.style.width = ws.value + 'px'; };
    const input = root.dataset.input ? document.getElementById(root.dataset.input) : null;
    function place(i, animate) {
      if (i < 0) i = 0;
      const cr = root.getBoundingClientRect(), br = btns[i].getBoundingClientRect();
      const x = br.left - cr.left, w = br.width;
      btns.forEach((b, j) => b.setAttribute('aria-pressed', String(j === i)));
      if (input && btns[i].dataset.value != null) input.value = btns[i].dataset.value;
      if (!animate || reduce || w === 0) { xs.value = x; xs.vel = 0; ws.value = w; ws.vel = 0; render(); return; }
      xs.to(x, { response: .38 }, render); ws.to(w, { response: .38 }, render);
    }
    const cur = () => btns.findIndex(b => b.getAttribute('aria-pressed') === 'true');
    btns.forEach((b, i) => b.addEventListener('click', () => { place(i, true); if (onChange) onChange(b); }));
    requestAnimationFrame(() => place(cur(), false));
    addEventListener('resize', () => place(cur(), false));
    return { place, reflow: () => place(cur(), false) };
  }

  /* theme */
  function applyTheme(t, fade) {
    const d = document.documentElement;
    if (fade && !reduce) { d.classList.add('theme-fade'); setTimeout(() => d.classList.remove('theme-fade'), 450); }
    d.setAttribute('data-theme', t);
    try { localStorage.setItem('es-theme', t); } catch (e) { /* storage unavailable */ }
    $$('[data-theme-label]').forEach(el => { el.textContent = t === 'dark' ? 'Dark' : 'Light'; });
  }
  function initThemeFab() {
    const fab = $('#themeFab'); if (!fab) return;
    fab.addEventListener('click', () => {
      const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      applyTheme(next, true);
      fab.setAttribute('aria-pressed', String(next === 'dark'));
    });
    fab.setAttribute('aria-pressed', String(document.documentElement.getAttribute('data-theme') === 'dark'));
  }
  document.addEventListener('DOMContentLoaded', initThemeFab);

  window.ES = { $, $$, reduce, Spring, toast, confirmModal, makeChips, applyTheme };
})();
