/* EntrySafe restriction request form: photo dropzone + consent checkbox (same look as registration). */
(function () {
  'use strict';
  const { $ } = window.ES;
  const form = $('#restrictionForm'); if (!form) return;

  const drop = $('#drop'), fileInput = $('#fileInput'), fileChip = $('#fileChip'), fileName = $('#fileName');
  if (drop && fileInput) {
    const show = () => {
      const f = fileInput.files[0];
      if (!f) { fileChip.classList.remove('show'); drop.style.display = ''; return; }
      fileName.textContent = f.name; fileChip.classList.add('show'); drop.style.display = 'none';
    };
    drop.addEventListener('click', () => fileInput.click());
    drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
    fileInput.addEventListener('change', show);
    ['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove('over')));
    drop.addEventListener('drop', e => {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; show(); }
    });
    $('#fileRemove').addEventListener('click', () => { fileInput.value = ''; show(); });
  }

  const consent = $('#consent'), consentInput = $('#consentInput'), submitBtn = $('#submitRequest');
  if (consent && consentInput) {
    const sync = () => { consent.setAttribute('aria-checked', String(consentInput.checked)); if (submitBtn) submitBtn.disabled = !consentInput.checked; };
    const toggle = () => { consentInput.checked = !consentInput.checked; sync(); };
    consent.addEventListener('click', toggle);
    consent.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
    sync();
  }
})();
