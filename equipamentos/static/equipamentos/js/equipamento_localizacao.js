(function () {
    const select = document.getElementById("id_cliente");
    const localizacao = document.getElementById("id_localizacao");
    const dadosElemento = document.getElementById("clientes-enderecos-equipamento");
    if (!select || !localizacao || !dadosElemento) return;

    let enderecos = {};
    try {
        const dados = JSON.parse(dadosElemento.textContent);
        if (dados && typeof dados === "object" && !Array.isArray(dados)) {
            enderecos = dados;
        }
    } catch (erro) {
        return;
    }

    const aplicar = () => {
        if (!select.value) return;
        const endereco = enderecos[String(select.value)];
        localizacao.value = endereco || "";
    };

    select.addEventListener("change", aplicar);
})();
