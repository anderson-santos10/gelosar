/* ============================================================
   GELOSAR - DASHBOARD DO CLIENTE
   Controle de dados sensíveis + progresso de equipamentos
============================================================ */


/* ============================================================
   CONTROLE DE DADOS SENSÍVEIS
   Individual
============================================================ */

function toggleSensitive(button) {
    if (!button) return;

    const container =
        button.closest('.kpi-card') ||
        button.closest('.history-value') ||
        button.closest('.gs-card');

    if (!container) return;

    const values = container.querySelectorAll('.sensitive-value');
    const masks = container.querySelectorAll('.sensitive-masked');
    const icon = button.querySelector('i');

    if (!values.length && !masks.length) return;

    const isHidden = values[0].classList.contains('d-none');

    values.forEach(value => {
        value.classList.toggle('d-none', !isHidden);
    });

    masks.forEach(mask => {
        mask.classList.toggle('d-none', isHidden);
    });

    if (icon) {
        icon.className = isHidden
            ? 'bi bi-eye-slash'
            : 'bi bi-eye';
    }

    const label = isHidden
        ? 'Ocultar valor'
        : 'Mostrar valor';

    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
}


/* ============================================================
   CONTROLE DE DADOS SENSÍVEIS
   Container completo
============================================================ */

function toggleSensitiveContainer(containerId, button) {
    if (!containerId || !button) return;

    const container = document.getElementById(containerId);

    if (!container) return;

    const values = container.querySelectorAll('.sensitive-value');
    const masks = container.querySelectorAll('.sensitive-masked');
    const icon = button.querySelector('i');

    if (!values.length && !masks.length) return;

    const isHidden = values.length > 0 &&
        values[0].classList.contains('d-none');

    values.forEach(value => {
        value.classList.toggle('d-none', !isHidden);
    });

    masks.forEach(mask => {
        mask.classList.toggle('d-none', isHidden);
    });

    if (icon) {
        icon.className = isHidden
            ? 'bi bi-eye-slash'
            : 'bi bi-eye';
    }

    const label = isHidden
        ? 'Ocultar valores'
        : 'Mostrar valores';

    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
}


function bindSensitiveToggles(event) {
    const containerButton = event.target.closest('[data-gs-sensitive-container]');
    if (containerButton) {
        event.preventDefault();
        toggleSensitiveContainer(
            containerButton.getAttribute('data-gs-sensitive-container'),
            containerButton
        );
        return;
    }

    const button = event.target.closest('[data-gs-sensitive]');
    if (!button) return;

    event.preventDefault();
    toggleSensitive(button);
}

document.addEventListener('click', bindSensitiveToggles);


/* ============================================================
   PROGRESSO DOS EQUIPAMENTOS
============================================================ */

document.addEventListener('DOMContentLoaded', function () {

    /* --------------------------------------------------------
       Formatação monetária
    -------------------------------------------------------- */

    function formatMoney(value) {
        return new Intl.NumberFormat('pt-BR', {
            style: 'currency',
            currency: 'BRL'
        }).format(value);
    }


    /* --------------------------------------------------------
       Calcula progresso de cada equipamento
    -------------------------------------------------------- */

    document.querySelectorAll('.equipment-progress').forEach(wrapper => {

        const equipmentAttribute =
            wrapper.getAttribute('data-equipment-value') || '0';

        const clientTotalAttribute =
            wrapper.getAttribute('data-client-total') || '0';


        const equipmentValue = parseFloat(
            equipmentAttribute
                .replace(/\./g, '')
                .replace(',', '.')
        ) || 0;


        const clientTotal = parseFloat(
            clientTotalAttribute
                .replace(/\./g, '')
                .replace(',', '.')
        ) || 0;


        if (equipmentValue <= 0) return;


        const paid = Math.min(clientTotal, equipmentValue);

        const remaining = Math.max(
            0,
            equipmentValue - paid
        );

        const percentage = Math.min(
            100,
            Math.round((paid / equipmentValue) * 100)
        );


        /* ----------------------------------------------------
           Elementos
        ---------------------------------------------------- */

        const circle =
            wrapper.querySelector('.progress-circle');

        const circleValue =
            wrapper.querySelector('.progress-circle-value');

        const bar =
            wrapper.querySelector('.equipment-progress-bar-fill');

        const paidValue =
            wrapper.querySelector('.progress-paid');

        const paidDetail =
            wrapper.querySelector('.progress-paid-detail');

        const remainingValue =
            wrapper.querySelector('.progress-remaining');


        /* ----------------------------------------------------
           Círculo
        ---------------------------------------------------- */

        if (circle) {
            circle.style.setProperty(
                '--progress',
                percentage
            );
        }


        if (circleValue) {
            circleValue.textContent =
                `${percentage}%`;
        }


        /* ----------------------------------------------------
           Barra
        ---------------------------------------------------- */

        if (bar) {
            bar.style.width =
                `${percentage}%`;
        }


        /* ----------------------------------------------------
           Valores
        ---------------------------------------------------- */

        if (paidValue) {
            paidValue.textContent =
                formatMoney(paid);
        }


        if (paidDetail) {
            paidDetail.textContent =
                formatMoney(paid);
        }


        if (remainingValue) {
            remainingValue.textContent =
                formatMoney(remaining);
        }


        /* ----------------------------------------------------
           Equipamento quitado
        ---------------------------------------------------- */

        if (percentage >= 100) {
            wrapper.classList.add(
                'equipment-progress-complete'
            );
        }

    });

});


/* ============================================================
   HISTÓRICO DE COMPRAS
============================================================ */

document.addEventListener('DOMContentLoaded', function () {

    const historyButtons =
        document.querySelectorAll(
            '.history-header-btn, .history-date'
        );

    historyButtons.forEach(function (button) {

        const targetId =
            button.getAttribute(
                'data-bs-target'
            );

        if (!targetId) return;

        const target =
            document.querySelector(targetId);

        if (!target) return;

        /*
         * O Bootstrap controla a abertura/fechamento.
         * Listeners permanentes sincronizam aria-expanded
         * em todos os ciclos (abrir / fechar / reabrir).
         */

        target.addEventListener(
            'shown.bs.collapse',
            function () {
                button.setAttribute(
                    'aria-expanded',
                    'true'
                );
            }
        );

        target.addEventListener(
            'hidden.bs.collapse',
            function () {
                button.setAttribute(
                    'aria-expanded',
                    'false'
                );
            }
        );

    });

});
