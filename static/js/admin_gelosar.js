document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("toggle-nav-sidebar");
    const sidebar = document.getElementById("nav-sidebar");
    if (!toggle || !sidebar) return;

    const isMobile = () => window.matchMedia("(max-width: 767.98px)").matches;

    const sync = () => {
        const expanded = sidebar.getAttribute("aria-expanded") === "true";
        document.body.classList.toggle("gs-admin-is-mobile-open", isMobile() && expanded);
        sidebar.classList.toggle("is-expanded", expanded);
        sidebar.classList.toggle("is-mobile-open", isMobile() && expanded);
    };

    toggle.addEventListener("click", () => {
        window.setTimeout(sync, 0);
    });

    window.matchMedia("(max-width: 767.98px)").addEventListener("change", sync);
    sync();
});
