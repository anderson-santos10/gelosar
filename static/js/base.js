document.addEventListener('DOMContentLoaded', () => {
    const navbar = document.getElementById('gsNavbar');
    const toggleBtn = document.getElementById('gsNavToggle');
    const panel = document.getElementById('gsNavPanel');
    const overlay = document.getElementById('gsNavOverlay');

    const dropdownRoots = navbar
        ? Array.from(navbar.querySelectorAll('.has-dropdown, .gs-user'))
        : [];

    const isMobileNav = () => window.matchMedia('(max-width: 991.98px)').matches;

    const setExpanded = (trigger, expanded) => {
        if (!trigger) return;
        trigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        if (trigger === toggleBtn) {
            trigger.setAttribute('aria-label', expanded ? 'Fechar menu' : 'Abrir menu');
        }
    };

    const closeDropdowns = (exceptRoot = null) => {
        dropdownRoots.forEach((root) => {
            if (root === exceptRoot) return;
            root.classList.remove('is-open');
            const trigger = root.querySelector('.gs-nav__trigger, .gs-user__trigger');
            setExpanded(trigger, false);
        });
    };

    const closeMobileNav = () => {
        document.body.classList.remove('gs-nav-open');
        panel?.classList.remove('is-open');
        overlay?.classList.remove('is-open');
        overlay?.setAttribute('hidden', '');
        setExpanded(toggleBtn, false);
        closeDropdowns();
    };

    const openMobileNav = () => {
        document.body.classList.add('gs-nav-open');
        panel?.classList.add('is-open');
        overlay?.classList.add('is-open');
        overlay?.removeAttribute('hidden');
        setExpanded(toggleBtn, true);
    };

    if (toggleBtn && panel && overlay) {
        toggleBtn.addEventListener('click', () => {
            const willOpen = !panel.classList.contains('is-open');
            if (willOpen) {
                openMobileNav();
            } else {
                closeMobileNav();
            }
        });

        overlay.addEventListener('click', closeMobileNav);
    }

    dropdownRoots.forEach((root) => {
        const trigger = root.querySelector('.gs-nav__trigger, .gs-user__trigger');
        if (!trigger) return;

        trigger.addEventListener('click', (event) => {
            event.preventDefault();
            const willOpen = !root.classList.contains('is-open');
            closeDropdowns(willOpen ? root : null);
            root.classList.toggle('is-open', willOpen);
            setExpanded(trigger, willOpen);
        });
    });

    document.addEventListener('click', (event) => {
        if (!navbar?.contains(event.target)) {
            closeDropdowns();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;

        if (document.body.classList.contains('gs-nav-open')) {
            closeMobileNav();
            toggleBtn?.focus();
            return;
        }

        closeDropdowns();
    });

    window.addEventListener('resize', () => {
        if (!isMobileNav()) {
            closeMobileNav();
        }
    });

    document.querySelectorAll('[data-gs-dismiss="alert"]').forEach((button) => {
        button.addEventListener('click', () => {
            button.closest('.gs-alert')?.remove();
        });
    });

    document.addEventListener('click', (event) => {
        if (event.target.closest('[data-gs-print]')) {
            window.print();
        }
    });
});
