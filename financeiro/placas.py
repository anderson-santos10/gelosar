import re

UFS_BRASIL = [
    ("AC", "Acre"),
    ("AL", "Alagoas"),
    ("AP", "Amapá"),
    ("AM", "Amazonas"),
    ("BA", "Bahia"),
    ("CE", "Ceará"),
    ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"),
    ("GO", "Goiás"),
    ("MA", "Maranhão"),
    ("MT", "Mato Grosso"),
    ("MS", "Mato Grosso do Sul"),
    ("MG", "Minas Gerais"),
    ("PA", "Pará"),
    ("PB", "Paraíba"),
    ("PR", "Paraná"),
    ("PE", "Pernambuco"),
    ("PI", "Piauí"),
    ("RJ", "Rio de Janeiro"),
    ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"),
    ("RO", "Rondônia"),
    ("RR", "Roraima"),
    ("SC", "Santa Catarina"),
    ("SP", "São Paulo"),
    ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]

PLACA_ANTIGA = re.compile(r"^[A-Z]{3}[0-9]{4}$")
PLACA_MERCOSUL = re.compile(r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$")


def normalizar_placa(valor):
    if not valor:
        return ""
    return "".join(caractere for caractere in str(valor).upper() if caractere.isalnum())


def formatar_placa(valor):
    placa = normalizar_placa(valor)
    if PLACA_ANTIGA.match(placa):
        return f"{placa[:3]}-{placa[3:]}"
    return placa


def placa_valida(valor):
    placa = normalizar_placa(valor)
    return bool(PLACA_ANTIGA.match(placa) or PLACA_MERCOSUL.match(placa))


def normalizar_renavam(valor):
    if not valor:
        return ""
    return "".join(caractere for caractere in str(valor) if caractere.isdigit())
