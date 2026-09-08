(function () {
    let iniciado = false;

    const formatarMoeda = (valor) => {
        return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    };

    const carregarPrecos = () => {
        const precosDataElement = document.getElementById('produtos-precos-data');
        if (!precosDataElement) return {};

        try {
            const dados = JSON.parse(precosDataElement.textContent);
            if (!dados || typeof dados !== 'object' || Array.isArray(dados)) {
                return {};
            }
            return dados;
        } catch (erro) {
            return {};
        }
    };

    const paraCentavos = (valor) => {
        const numero = Number(valor);
        if (!Number.isFinite(numero)) return 0;
        return Math.round(numero * 100);
    };

    const obterCampos = (row) => {
        return {
            produtoSelect: row.querySelector('.produto-select') || row.querySelector('select[name$="-produto"]'),
            quantidadeInput: row.querySelector('.quantidade-input') || row.querySelector('input[name$="-quantidade"]')
        };
    };

    const iniciarCalculoVenda = () => {
        if (iniciado) return;
        iniciado = true;

        const precosProdutos = carregarPrecos();
        const container = document.getElementById('itens-container');
        const totalForms = document.querySelector('input[name$="-TOTAL_FORMS"]');
        const template = document.getElementById('empty-form-template');
        const btnAdicionar = document.getElementById('btn-adicionar-produto');

        const atualizarLinha = (row) => {
            const { produtoSelect, quantidadeInput } = obterCampos(row);
            const precoInput = row.querySelector('.preco-input');
            const subtotalSpan = row.querySelector('.subtotal');

            if (!produtoSelect || !quantidadeInput) return;

            const produtoId = produtoSelect.value;
            const quantidade = Number(quantidadeInput.value);
            const quantidadeValida = Number.isFinite(quantidade) ? quantidade : 0;
            const precoCentavos = paraCentavos(precosProdutos[produtoId]);
            const subtotalCentavos = Math.round(quantidadeValida * precoCentavos);
            const precoUnitario = precoCentavos / 100;
            const subtotal = subtotalCentavos / 100;

            if (precoInput) precoInput.value = formatarMoeda(precoUnitario);
            if (subtotalSpan) subtotalSpan.textContent = formatarMoeda(subtotal);

            atualizarTotal();
        };

        const atualizarTotal = () => {
            let totalCentavos = 0;

            document.querySelectorAll('.item-row').forEach(row => {
                if (row.style.display === 'none') return;

                const deleteInput = row.querySelector('input[name$="-DELETE"]');
                if (deleteInput && (deleteInput.checked || deleteInput.value === 'on')) {
                    return;
                }

                const { produtoSelect, quantidadeInput } = obterCampos(row);
                if (!produtoSelect || !quantidadeInput) return;

                const produtoId = produtoSelect.value;
                const quantidade = Number(quantidadeInput.value);
                const quantidadeValida = Number.isFinite(quantidade) ? quantidade : 0;
                const precoCentavos = paraCentavos(precosProdutos[produtoId]);
                totalCentavos += Math.round(quantidadeValida * precoCentavos);
            });

            const totalElement = document.getElementById('total-venda');
            if (totalElement) {
                totalElement.textContent = formatarMoeda(totalCentavos / 100);
            }
        };

        const garantirCampoDelete = (row) => {
            let deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput) return deleteInput;

            const produtoSelect =
                row.querySelector('.produto-select') ||
                row.querySelector('select[name$="-produto"]');
            if (!produtoSelect || !produtoSelect.name) return null;

            deleteInput = document.createElement('input');
            deleteInput.type = 'hidden';
            deleteInput.name = produtoSelect.name.replace(/-produto$/, '-DELETE');
            row.prepend(deleteInput);
            return deleteInput;
        };

        const removerItem = (row) => {
            if (!row) return;

            const deleteInput = garantirCampoDelete(row);
            if (!deleteInput) return;

            deleteInput.value = 'on';
            deleteInput.checked = true;
            row.style.display = 'none';

            atualizarTotal();
        };

        const configurarLinha = (row) => {
            const { produtoSelect, quantidadeInput } = obterCampos(row);

            if (produtoSelect) {
                produtoSelect.classList.add('form-control', 'produto-select');
                produtoSelect.addEventListener('change', () => atualizarLinha(row));
            }

            if (quantidadeInput) {
                quantidadeInput.classList.add('form-control', 'quantidade-input');
                ['input', 'change'].forEach(evento => {
                    quantidadeInput.addEventListener(evento, () => atualizarLinha(row));
                });
            }

            const btnRemover = row.querySelector('.btn-remover');
            if (btnRemover) {
                btnRemover.addEventListener('click', () => removerItem(row));
            }

            atualizarLinha(row);
        };

        const adicionarItem = () => {
            if (!container || !totalForms || !template) {
                console.error('Configuração do formset inválida. Verifique os IDs no HTML.');
                return;
            }

            const count = parseInt(totalForms.value, 10);
            const newRowHTML = template.innerHTML.replace(/__prefix__/g, count);

            const tempDiv = document.createElement('tbody');
            tempDiv.innerHTML = newRowHTML.trim();
            const novaLinha = tempDiv.firstElementChild;

            if (!novaLinha) return;

            container.appendChild(novaLinha);
            totalForms.value = count + 1;

            configurarLinha(novaLinha);
        };

        if (btnAdicionar) {
            btnAdicionar.addEventListener('click', adicionarItem);
        }

        document.querySelectorAll('.item-row').forEach(row => {
            configurarLinha(row);
        });

        atualizarTotal();
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciarCalculoVenda);
    } else {
        iniciarCalculoVenda();
    }
})();
