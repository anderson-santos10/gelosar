(function () {
    function token(nome, fallback) {
        const valor = getComputedStyle(document.documentElement)
            .getPropertyValue(nome)
            .trim();
        return valor || fallback;
    }

    function paleta() {
        return [
            token('--gs-primary', '#0B63C5'),
            token('--gs-navy', '#0B2C5C'),
            token('--gs-primary-hover', '#094F9E'),
        ];
    }

    function formatarMoeda(valor) {
        return Number(valor).toLocaleString('pt-BR', {
            style: 'currency',
            currency: 'BRL',
        });
    }

    function iniciarGraficos() {
        if (typeof Chart === 'undefined') return;

        const cores = paleta();

        document.querySelectorAll('canvas[data-gs-chart]').forEach((canvas) => {
            const payloadId = canvas.getAttribute('data-gs-chart');
            const payloadEl = document.getElementById(payloadId);
            if (!payloadEl) return;

            let payload;
            try {
                payload = JSON.parse(payloadEl.textContent);
            } catch (erro) {
                return;
            }
            if (!payload || !Array.isArray(payload.labels)) return;

            const datasets = payload.datasets
                ? payload.datasets.map((dataset, indice) => ({
                    ...dataset,
                    backgroundColor: dataset.backgroundColor || cores[indice % cores.length],
                    borderRadius: 6,
                    maxBarThickness: 36,
                }))
                : [{
                    label: payload.label || '',
                    data: payload.values || [],
                    backgroundColor: cores[0],
                    borderRadius: 6,
                    maxBarThickness: 36,
                }];

            const monetario = Boolean(payload.currency);

            new Chart(canvas, {
                type: payload.type || 'bar',
                data: {
                    labels: payload.labels,
                    datasets,
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: Boolean(payload.showLegend) || datasets.length > 1,
                        },
                        tooltip: {
                            callbacks: {
                                label(contexto) {
                                    const bruto = contexto.parsed.y;
                                    if (monetario) {
                                        return `${contexto.dataset.label}: ${formatarMoeda(bruto)}`;
                                    }
                                    return `${contexto.dataset.label}: ${bruto}`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                        },
                        y: {
                            beginAtZero: true,
                            ticks: monetario
                                ? {
                                    callback(valor) {
                                        return formatarMoeda(valor);
                                    },
                                }
                                : { precision: 0 },
                        },
                    },
                },
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciarGraficos);
    } else {
        iniciarGraficos();
    }
})();
