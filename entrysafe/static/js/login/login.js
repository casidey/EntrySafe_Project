// Feature JS: Login
document.addEventListener('DOMContentLoaded', function() {
    // Role selection behavior
    const rolePills = document.querySelectorAll('.clay-role-pill');
    rolePills.forEach(pill => {
        pill.addEventListener('click', () => {
            rolePills.forEach(p => {
                p.classList.remove('clay-role-pill-active');
                p.classList.add('text-on-surface-variant', 'font-medium');
                p.classList.remove('font-semibold');
            });
            pill.classList.add('clay-role-pill-active', 'font-semibold');
            pill.classList.remove('text-on-surface-variant', 'font-medium');
        });
    });
});
