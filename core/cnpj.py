from django.core.exceptions import ValidationError

MENSAGEM_CPF_CNPJ_DIGITOS = (
    "Informe um CNPJ com 14 dígitos ou um CPF com 11 dígitos."
)


def apenas_digitos(valor):
    if not valor:
        return ""
    return "".join(caractere for caractere in str(valor) if caractere.isdigit())


def normalizar_cnpj(valor):
    """Armazena só dígitos para consulta e unicidade. Vazio vira None."""
    digitos = apenas_digitos(valor)
    return digitos or None


def validar_digitos_cpf_cnpj(valor):
    """Normaliza e exige 11 (CPF) ou 14 (CNPJ) dígitos quando informado."""
    normalizado = normalizar_cnpj(valor)
    if normalizado is None:
        return None
    if len(normalizado) not in (11, 14):
        raise ValidationError(MENSAGEM_CPF_CNPJ_DIGITOS)
    return normalizado


def formatar_cnpj_cpf(valor):
    """Formata CNPJ (14 dígitos) ou CPF (11 dígitos) no padrão brasileiro."""
    if not valor:
        return ""
    digitos = apenas_digitos(valor)
    if len(digitos) == 14:
        return (
            f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/"
            f"{digitos[8:12]}-{digitos[12:]}"
        )
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return str(valor).strip()
