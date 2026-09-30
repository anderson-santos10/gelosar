(function () {
    const iniciar = () => {
        const select = document.querySelector(".js-cliente-pedido");
        const busca = document.getElementById("busca-cliente");
        const endereco = document.getElementById("id_endereco");
        const cidade = document.getElementById("id_cidade");
        const dadosElemento = document.getElementById("clientes-enderecos-data");
        const precosElemento = document.getElementById("produtos-precos-data");
        const container = document.getElementById("itens-container");
        const totalForms = document.querySelector('input[name$="-TOTAL_FORMS"]');
        const template = document.getElementById("empty-form-template");
        const btnAdicionar = document.getElementById("btn-adicionar-produto");
        const totalPedido = document.getElementById("total-pedido");

        let enderecos = {};
        let precos = {};

        const lerJson = (elemento) => {
            if (!elemento) return {};
            try {
                const dados = JSON.parse(elemento.textContent);
                if (dados && typeof dados === "object" && !Array.isArray(dados)) return dados;
            } catch (erro) {
                return {};
            }
            return {};
        };

        enderecos = lerJson(dadosElemento);
        precos = lerJson(precosElemento);

        const formatar = (centavos) => {
            return (centavos / 100).toLocaleString("pt-BR", {
                style: "currency",
                currency: "BRL",
            });
        };

        const centavosDe = (valor) => {
            const numero = Number(valor);
            if (!Number.isFinite(numero)) return 0;
            return Math.round(numero * 100);
        };

        const atualizarCard = (card) => {
            const produto = card.querySelector('select[name$="-produto"]');
            const quantidade = card.querySelector('input[name$="-quantidade"]');
            const preco = card.querySelector(".preco-unitario");
            const subtotal = card.querySelector(".subtotal");
            if (!produto || !quantidade) return 0;
            const unitario = centavosDe(precos[produto.value]);
            const qtd = Number(quantidade.value);
            const qtdValida = Number.isFinite(qtd) ? qtd : 0;
            const parcial = Math.round(qtdValida * unitario);
            if (preco) preco.textContent = formatar(unitario);
            if (subtotal) subtotal.textContent = formatar(parcial);
            return parcial;
        };

        const atualizarTotal = () => {
            let total = 0;
            document.querySelectorAll(".item-row").forEach((card) => {
                if (card.hidden) return;
                const apagar = card.querySelector('input[name$="-DELETE"]');
                if (apagar && (apagar.checked || apagar.value === "on")) return;
                total += atualizarCard(card);
            });
            if (totalPedido) totalPedido.textContent = formatar(total);
        };

        if (select) {
            select.addEventListener("change", () => {
                const dados = enderecos[select.value];
                if (!dados) return;
                if (endereco) endereco.value = dados.endereco || "";
                if (cidade) cidade.value = dados.cidade || "";
            });
        }

        if (busca && select) {
            const opcoes = Array.from(select.options).map((option) => ({
                value: option.value,
                text: option.textContent,
            }));
            busca.addEventListener("input", () => {
                const termo = busca.value.trim().toLocaleLowerCase("pt-BR");
                const selecionado = select.value;
                const fragmento = document.createDocumentFragment();
                opcoes.forEach((item) => {
                    const texto = item.text.toLocaleLowerCase("pt-BR");
                    const visivel = !item.value || !termo || texto.includes(termo) || item.value === selecionado;
                    if (!visivel) return;
                    const option = document.createElement("option");
                    option.value = item.value;
                    option.textContent = item.text;
                    if (item.value === selecionado) option.selected = true;
                    fragmento.appendChild(option);
                });
                select.replaceChildren(fragmento);
            });
        }

        const marcarRemocao = (card) => {
            let deleteInput = card.querySelector('input[name$="-DELETE"]');
            if (!deleteInput) {
                const produto = card.querySelector('select[name$="-produto"]');
                if (!produto || !produto.name) return;
                deleteInput = document.createElement("input");
                deleteInput.type = "hidden";
                deleteInput.name = produto.name.replace(/-produto$/, "-DELETE");
                card.prepend(deleteInput);
            }
            deleteInput.value = "on";
            deleteInput.checked = true;
            card.hidden = true;
            atualizarTotal();
        };

        const configurarCard = (card) => {
            const produto = card.querySelector('select[name$="-produto"]');
            const quantidade = card.querySelector('input[name$="-quantidade"]');
            const botao = card.querySelector(".btn-remover");
            if (produto) produto.addEventListener("change", atualizarTotal);
            if (quantidade) {
                quantidade.addEventListener("input", atualizarTotal);
                quantidade.addEventListener("change", atualizarTotal);
            }
            if (botao) botao.addEventListener("click", () => marcarRemocao(card));
        };

        if (btnAdicionar && container && totalForms && template) {
            btnAdicionar.addEventListener("click", () => {
                const indice = parseInt(totalForms.value, 10);
                if (!Number.isFinite(indice)) return;
                const apoio = document.createElement("div");
                apoio.innerHTML = template.innerHTML.replace(/__prefix__/g, String(indice)).trim();
                const novo = apoio.firstElementChild;
                if (!novo) return;
                container.appendChild(novo);
                totalForms.value = String(indice + 1);
                configurarCard(novo);
                atualizarTotal();
            });
        }

        document.querySelectorAll(".item-row").forEach(configurarCard);
        atualizarTotal();
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
