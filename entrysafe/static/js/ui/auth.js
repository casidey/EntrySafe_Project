/* EntrySafe auth pages: password reveal, 2-step registration slide, dropzone, consent, submitted modal. */
(function () {
  'use strict';
  const { $, $$, reduce, Spring, makeChips } = window.ES;

  $$('.eye').forEach(btn => btn.addEventListener('click', () => {
    const inp = document.getElementById(btn.dataset.toggle), show = inp.type === 'password';
    inp.type = show ? 'text' : 'password';
    btn.innerHTML = show ? '<svg><use href="#i-eye-off"/></svg>' : '<svg><use href="#i-eye"/></svg>';
    btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  }));

  /* ---------- registration ---------- */
  const track = $('#track');
  if (track) {
    const progBars = [$('#prog1'), $('#prog2')];
    const screens = $$('.screen', track);
    const pos = new Spring(0);
    const setProgress = (i) => { progBars[0].style.width = i >= 1 ? '100%' : '0%'; progBars[1].style.width = i >= 2 ? '100%' : '0%'; };
    function goTo(i, animate) {
      const paint = v => { track.style.transform = `translate3d(${(-v / screens.length) * 100}%,0,0)`; };
      if (animate === false) { pos.value = i; pos.vel = 0; paint(i); } else pos.to(i, { response: .5 }, paint);
      setProgress(i + 1);
      screens.forEach((s, j) => { s.toggleAttribute('inert', j !== i); });
      if (screens[i]) screens[i].scrollTop = 0;
      if (i === 1) towerChips.reflow();
    }
    const towerChips = makeChips($('#towerChips'));

    const step1Inputs = $$('input', screens[0]);
    const next = () => { for (const i of step1Inputs) { if (!i.reportValidity()) return; } goTo(1); };
    $('#step1Next').addEventListener('click', next);
    screens[0].addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); next(); } });
    $('#backToStep1').addEventListener('click', () => goTo(0));

    const drop = $('#drop'), fileInput = $('#fileInput'), fileChip = $('#fileChip'), fileName = $('#fileName');
    const consent = $('#consent'), consentInput = $('#consentInput'), submitBtn = $('#submitReg');
    const MAX = 15 * 1024 * 1024;
    function check() {
      submitBtn.disabled = !($('#r-unit').value.trim() && fileInput.files.length && consentInput.checked);
    }
    function showFile() {
      const f = fileInput.files[0]; if (!f) return;
      if (f.size > MAX) { fileInput.value = ''; window.ES.toast('That file is larger than 15MB.'); return check(); }
      fileName.textContent = f.name; fileChip.classList.add('show'); drop.style.display = 'none'; check();
    }
    drop.addEventListener('click', () => fileInput.click());
    drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
    fileInput.addEventListener('change', showFile);
    ['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove('over')));
    drop.addEventListener('drop', e => {
      e.preventDefault();
      if (e.dataTransfer.files[0]) { const dt = new DataTransfer(); dt.items.add(e.dataTransfer.files[0]); fileInput.files = dt.files; showFile(); }
    });
    $('#fileRemove').addEventListener('click', () => { fileInput.value = ''; fileChip.classList.remove('show'); drop.style.display = ''; check(); });

    const toggleConsent = () => { consentInput.checked = !consentInput.checked; consent.setAttribute('aria-checked', String(consentInput.checked)); check(); };
    consent.addEventListener('click', toggleConsent);
    consent.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleConsent(); } });
    $('#r-unit').addEventListener('input', check);
    check();

    goTo(parseInt(track.dataset.startStep || '0', 10), false);
  }

  /* ---------- "submitted for review" modal on the sign-in page ---------- */
  const modal = $('#modal'), scrim = $('#scrim');
  if (modal && scrim) {
    requestAnimationFrame(() => setTimeout(() => { scrim.classList.add('show'); modal.classList.add('show'); }, 250));
    const close = () => { scrim.classList.remove('show'); modal.classList.remove('show'); };
    $('#modalDone').addEventListener('click', close); scrim.addEventListener('click', close);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  }
})();
