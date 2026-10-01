(function () {
    function token(nome, fallback) {
        const valor = getComputedStyle(document.documentElement)
            .getPropertyValue(nome)
            .trim();
        return valor || fallback;
    }

    function paleta() {
        return [
            token("--gs-hud-blue", "#3D9BFF"),
            token("--gs-hud-blue-2", "#7EC8FF"),
            token("--gs-hud-muted", "#A9BED4"),
            token("--gs-hud-track", "#163456"),
        ];
    }

    function formatarMoeda(valor) {
        return Number(valor).toLocaleString("pt-BR", {
            style: "currency",
            currency: "BRL",
        });
    }

    function formatarQuantidade(valor) {
        const numero = Number(valor);
        if (!Number.isFinite(numero)) {
            return String(valor);
        }
        if (Math.abs(numero - Math.trunc(numero)) < 1e-9) {
            return String(Math.trunc(numero));
        }
        return numero.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
    }

    function valorGrafico(contexto, anel) {
        if (anel) {
            return contexto.parsed;
        }
        if (contexto.parsed && typeof contexto.parsed === "object") {
            if (typeof contexto.parsed.y === "number") {
                return contexto.parsed.y;
            }
            if (typeof contexto.parsed.x === "number") {
                return contexto.parsed.x;
            }
        }
        return contexto.parsed;
    }

    const centro = {
        id: "gsHudCentro",
        afterDraw(chart) {
            const tipo = chart.config.type;
            if (tipo !== "doughnut" && tipo !== "pie") {
                return;
            }
            const dataset = chart.data.datasets[0];
            const area = chart.chartArea;
            if (!dataset || !area) {
                return;
            }
            const total = dataset.data.reduce(function (soma, valor) {
                return soma + (Number(valor) || 0);
            }, 0);
            const moeda = chart.options.plugins.gsHud && chart.options.plugins.gsHud.moeda;
            const texto = moeda
                ? formatarMoeda(total)
                : String(Math.round(total));
            const ctx = chart.ctx;
            const fonte = token("--gs-font-family", "Inter, sans-serif");
            ctx.save();
            ctx.font = "700 1.35rem " + fonte;
            ctx.fillStyle = token("--gs-hud-text", "#F7FBFF");
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(texto, (area.left + area.right) / 2, (area.top + area.bottom) / 2);
            ctx.restore();
        },
    };

    function desenhar(canvas, payload) {
        const cores = paleta();
        const tipo = payload.type || "bar";
        const anel = tipo === "doughnut" || tipo === "pie";
        const corTexto = token("--gs-hud-muted", "#A9BED4");
        const corGrade = token("--gs-hud-grid", "rgba(169, 190, 212, 0.16)");
        const fonte = token("--gs-font-family", "Inter, sans-serif");
        const datasets = payload.datasets
            ? payload.datasets.map(function (dataset, indice) {
                return Object.assign({}, dataset, {
                    backgroundColor: dataset.backgroundColor || cores[indice % cores.length],
                    borderColor: token("--gs-hud-bg", "#071E40"),
                    borderWidth: anel ? 2 : 0,
                    borderRadius: anel ? 0 : 8,
                    maxBarThickness: 28,
                });
            })
            : [{
                label: payload.label || "",
                data: payload.values || [],
                backgroundColor: anel
                    ? (payload.labels || []).map(function (_, indice) {
                        return cores[indice % cores.length];
                    })
                    : cores[0],
                borderColor: token("--gs-hud-bg", "#071E40"),
                borderWidth: anel ? 2 : 0,
                borderRadius: anel ? 0 : 8,
                maxBarThickness: 28,
            }];
        const ticks = payload.currency
            ? {
                color: corTexto,
                callback(valor) {
                    return formatarMoeda(valor);
                },
            }
            : { color: corTexto, precision: 0 };
        const horizontal = payload.indexAxis === "y";
        const escalas = anel
            ? {}
            : horizontal
                ? {
                    x: { beginAtZero: true, ticks: ticks, grid: { color: corGrade } },
                    y: { grid: { display: false }, ticks: { color: corTexto } },
                }
                : {
                    x: { grid: { display: false }, ticks: { color: corTexto } },
                    y: { beginAtZero: true, ticks: ticks, grid: { color: corGrade } },
                };

        return new Chart(canvas, {
            type: tipo,
            data: {
                labels: payload.labels,
                datasets: datasets,
            },
            plugins: [centro],
            options: {
                indexAxis: payload.indexAxis || "x",
                responsive: true,
                maintainAspectRatio: false,
                cutout: anel ? "68%" : undefined,
                font: { family: fonte },
                plugins: {
                    gsHud: { moeda: Boolean(payload.currency) },
                    legend: {
                        display: Boolean(payload.showLegend) || datasets.length > 1 || anel,
                        labels: {
                            color: corTexto,
                            boxWidth: 10,
                            font: { family: fonte },
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label(contexto) {
                                const bruto = valorGrafico(contexto, anel);
                                if (payload.currency) {
                                    return contexto.label + ": " + formatarMoeda(bruto);
                                }
                                const nome = contexto.dataset.label || contexto.label;
                                return nome + ": " + formatarQuantidade(bruto);
                            },
                        },
                    },
                },
                scales: escalas,
            },
        });
    }

    function iniciar(raiz) {
        if (typeof Chart === "undefined") {
            return;
        }
        const escopo = raiz || document;
        escopo.querySelectorAll("canvas[data-gs-chart]").forEach(function (canvas) {
            if (canvas.dataset.gsChartPronto === "1") {
                return;
            }
            const payloadEl = document.getElementById(canvas.getAttribute("data-gs-chart"));
            if (!payloadEl) {
                return;
            }
            let payload;
            try {
                payload = JSON.parse(payloadEl.textContent);
            } catch (erro) {
                return;
            }
            if (!payload || !Array.isArray(payload.labels) || !payload.labels.length) {
                return;
            }
            canvas.dataset.gsChartPronto = "1";
            desenhar(canvas, payload);
        });
    }

    window.GsCharts = { iniciar: iniciar };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            iniciar(document);
        });
    } else {
        iniciar(document);
    }
})();
