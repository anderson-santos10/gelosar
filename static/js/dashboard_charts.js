(function () {
    function iniciar() {
        if (window.GsCharts) {
            window.GsCharts.iniciar(document);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
