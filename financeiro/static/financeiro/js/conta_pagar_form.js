(function () {
    const status = document.getElementById("id_status");
    const pagamento = document.getElementById("id_data_pagamento");
    if (status && pagamento) {
        const sincronizar = () => {
            if (status.value === "pendente") {
                pagamento.value = "";
            }
        };
        status.addEventListener("change", sincronizar);
    }

    const form = document.querySelector("form[data-exige-veiculo]");
    const categoria = document.getElementById("id_categoria");
    const veiculo = document.getElementById("id_veiculo");
    if (!form || !categoria || !veiculo) {
        return;
    }
    const ids = (form.getAttribute("data-exige-veiculo") || "")
        .split(",")
        .filter(Boolean);
    const atualizar = () => {
        const exige = ids.indexOf(categoria.value) !== -1;
        const grupo = veiculo.closest(".col-12, .col-md-4");
        if (grupo) {
            if (exige) {
                grupo.classList.remove("is-hidden");
            } else {
                grupo.classList.add("is-hidden");
            }
        }
    };
    categoria.addEventListener("change", atualizar);
    atualizar();
})();
