/* Settings page: switches save on change (no Save button); dark mode applies instantly. */
(function () {
  'use strict';
  const { $, $$, applyTheme } = window.ES;
  const form = $('#settingsForm'); if (!form) return;
  const state = $('#saveState');
  const csrf = form.querySelector('input[name=csrfmiddlewaretoken]').value;
  let timer = 0;

  function label(input) {
    const s = input.closest('.switchrow').querySelector('.state');
    if (s) s.textContent = input.checked ? 'On' : 'Off';
  }
  $$('input[type=checkbox]', form).forEach(label);

  async function save() {
    state.textContent = 'Saving…';
    const body = new FormData(form);
    try {
      const res = await fetch(form.action || location.href, {
        method: 'POST', body, credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf }
      });
      if (!res.ok) throw new Error(res.status);
      state.textContent = 'Saved';
    } catch (e) { state.textContent = 'Could not save — check your connection.'; }
    clearTimeout(timer); timer = setTimeout(() => { state.textContent = ''; }, 2200);
  }

  form.addEventListener('change', e => {
    const input = e.target; if (input.type !== 'checkbox') return;
    label(input);
    if (input.name === 'dark_mode') applyTheme(input.checked ? 'dark' : 'light', true);
    save();
  });
  form.addEventListener('submit', e => e.preventDefault());
})();
