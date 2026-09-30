(function () {
    const campo = document.getElementById("id_cnpj");
    if (!campo) {
        return;
    }

    const apenasDigitos = (valor) => valor.replace(/\D/g, "").slice(0, 14);

    const formatar = (valor) => {
        const digitos = apenasDigitos(valor);
        if (digitos.length <= 11) {
            return digitos
                .replace(/(\d{3})(\d)/, "$1.$2")
                .replace(/(\d{3})(\d)/, "$1.$2")
                .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
        }
        return digitos
            .replace(/(\d{2})(\d)/, "$1.$2")
            .replace(/(\d{3})(\d)/, "$1.$2")
            .replace(/(\d{3})(\d)/, "$1/$2")
            .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
    };

    const aplicarMascara = () => {
        campo.value = formatar(campo.value);
    };

    campo.addEventListener("input", aplicarMascara);
    aplicarMascara();
})();
