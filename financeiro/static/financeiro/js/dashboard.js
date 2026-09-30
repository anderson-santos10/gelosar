(function () {
    function iniciarGraficos() {
        if (window.GsCharts) {
            window.GsCharts.iniciar(document);
        }
    }

    function iniciarPeriodo() {
        const seletor = document.querySelector("[data-periodo-select]");
        const custom = document.querySelectorAll("[data-periodo-custom]");
        if (!seletor || !custom.length) {
            return;
        }
        const sincronizar = () => {
            const personalizado = seletor.value === "personalizado";
            custom.forEach((bloco) => {
                if (personalizado) {
                    bloco.classList.remove("is-hidden");
                } else {
                    bloco.classList.add("is-hidden");
                }
            });
        };
        seletor.addEventListener("change", sincronizar);
        sincronizar();
    }

    function iniciar() {
        iniciarPeriodo();
        iniciarGraficos();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
