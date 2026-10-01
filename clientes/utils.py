import re

from core.cnpj import apenas_digitos, formatar_cnpj_cpf, normalizar_cnpj

__all__ = [
    "apenas_digitos",
    "apresentar_cidade",
    "formatar_cnpj_cpf",
    "formatar_telefone",
    "normalizar_cnpj",
]

_CIDADE_UF = re.compile(
    r"^(?P<cidade>.+?)\s*[/\-–]\s*(?P<uf>[A-Za-z]{2})$"
)


def formatar_telefone(valor):
    """Formata telefone de 10 ou 11 dígitos. Mantém o texto quando não couber."""
    texto = (valor or "").strip()
    if not texto:
        return ""
    digitos = apenas_digitos(texto)
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return texto


def apresentar_cidade(valor):
    """Normaliza 'Cidade/UF' para 'Cidade - UF'. Não inventa UF."""
    texto = (valor or "").strip()
    if not texto:
        return ""
    encontrado = _CIDADE_UF.match(texto)
    if not encontrado:
        return texto
    cidade = encontrado.group("cidade").strip()
    uf = encontrado.group("uf").upper()
    if not cidade:
        return texto
    return f"{cidade} - {uf}"
