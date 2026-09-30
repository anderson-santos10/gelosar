(function () {
    const DEBOUNCE_MS = 400;

    function debounce(fn, espera) {
        let timer = 0;
        return function () {
            const contexto = this;
            const args = arguments;
            window.clearTimeout(timer);
            timer = window.setTimeout(function () {
                fn.apply(contexto, args);
            }, espera);
        };
    }

    function textoFiltros(quantidade) {
        if (!quantidade) {
            return "";
        }
        if (quantidade === 1) {
            return "1 filtro ativo";
        }
        return quantidade + " filtros ativos";
    }

    function initListaDinamica(raiz) {
        const form = raiz.querySelector("[data-lista-filtros]");
        const destino = raiz.querySelector("[data-lista-resultados]");
        const erro = raiz.querySelector("[data-lista-erro]");
        const status = raiz.querySelector("[data-lista-status]");
        const contador = raiz.querySelector("[data-filtros-contador]");
        if (!form || !destino) {
            return;
        }

        const urlBase = form.getAttribute("action") || window.location.pathname;
        let controlador = null;

        function esconderErro() {
            if (erro) {
                erro.hidden = true;
            }
        }

        function mostrarErro() {
            if (erro) {
                erro.hidden = false;
            }
        }

        function atualizarContador(quantidade) {
            if (contador) {
                contador.textContent = textoFiltros(quantidade);
            }
            raiz.querySelectorAll("[data-lista-limpar]").forEach(function (botao) {
                if (botao.tagName === "A" || botao.tagName === "BUTTON") {
                    botao.hidden = quantidade === 0;
                }
            });
        }

        function queryDoFormulario() {
            const dados = new FormData(form);
            const params = new URLSearchParams();
            dados.forEach(function (valor, chave) {
                const texto = String(valor).trim();
                if (texto) {
                    params.set(chave, texto);
                }
            });
            return params;
        }

        function sincronizarFormulario(params) {
            Array.prototype.forEach.call(form.elements, function (campo) {
                if (!campo.name) {
                    return;
                }
                const valor = params.get(campo.name) || "";
                if (campo.type === "checkbox" || campo.type === "radio") {
                    campo.checked = campo.value === valor;
                } else {
                    campo.value = valor;
                }
            });
        }

        function aplicarFragmento(html, quantidade) {
            destino.innerHTML = html;
            if (status) {
                destino.prepend(status);
            }
            atualizarContador(quantidade);
        }

        function buscar(params, modoHistorico) {
            const query = params.toString();
            const url = query ? urlBase + "?" + query : urlBase;
            if (controlador) {
                controlador.abort();
            }
            controlador = new AbortController();
            esconderErro();
            destino.classList.add("is-loading");
            destino.setAttribute("aria-busy", "true");
            if (status) {
                status.hidden = false;
            }
            return fetch(url, {
                method: "GET",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    Accept: "text/html",
                },
                signal: controlador.signal,
            })
                .then(function (resposta) {
                    if (!resposta.ok) {
                        throw new Error("falha");
                    }
                    return resposta.text();
                })
                .then(function (html) {
                    const envelope = document.createElement("div");
                    envelope.innerHTML = html.trim();
                    const fragmento = envelope.querySelector("[data-filtros-ativos]") || envelope;
                    const quantidade = parseInt(
                        fragmento.getAttribute("data-filtros-ativos") || "0",
                        10
                    );
                    aplicarFragmento(fragmento.outerHTML, quantidade);
                    if (modoHistorico === "push") {
                        window.history.pushState({}, "", url);
                    } else if (modoHistorico === "replace") {
                        window.history.replaceState({}, "", url);
                    }
                })
                .catch(function (erroReq) {
                    if (erroReq.name === "AbortError") {
                        return;
                    }
                    mostrarErro();
                })
                .finally(function () {
                    destino.classList.remove("is-loading");
                    destino.removeAttribute("aria-busy");
                    if (status) {
                        status.hidden = true;
                    }
                });
        }

        form.addEventListener("submit", function (evento) {
            evento.preventDefault();
            const params = queryDoFormulario();
            params.delete("page");
            buscar(params, "push");
        });

        const aoDigitar = debounce(function () {
            const params = queryDoFormulario();
            params.delete("page");
            buscar(params, "replace");
        }, DEBOUNCE_MS);

        form.querySelectorAll("[data-lista-debounce]").forEach(function (campo) {
            campo.addEventListener("input", aoDigitar);
        });

        form.addEventListener("change", function (evento) {
            if (!evento.target || evento.target.hasAttribute("data-lista-debounce")) {
                return;
            }
            const params = queryDoFormulario();
            params.delete("page");
            buscar(params, "push");
        });

        raiz.addEventListener("click", function (evento) {
            const limpar = evento.target.closest("[data-lista-limpar]");
            if (limpar && raiz.contains(limpar)) {
                evento.preventDefault();
                form.reset();
                Array.prototype.forEach.call(form.elements, function (campo) {
                    if (campo.name && campo.type !== "submit" && campo.type !== "button") {
                        campo.value = "";
                    }
                });
                buscar(new URLSearchParams(), "push");
                return;
            }
            const link = evento.target.closest("a");
            if (!link || !destino.contains(link) || !link.getAttribute("href")) {
                return;
            }
            if (link.hasAttribute("data-lista-limpar")) {
                return;
            }
            const destinoUrl = new URL(link.href, window.location.origin);
            if (destinoUrl.pathname !== urlBase) {
                return;
            }
            evento.preventDefault();
            buscar(destinoUrl.searchParams, "push");
        });

        window.addEventListener("popstate", function () {
            const params = new URLSearchParams(window.location.search);
            sincronizarFormulario(params);
            buscar(params, null);
        });
    }

    window.gsInitListaDinamica = initListaDinamica;

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-lista-dinamica]").forEach(initListaDinamica);
    });
})();
