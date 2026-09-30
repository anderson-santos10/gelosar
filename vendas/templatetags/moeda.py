from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name="moeda_br")
def moeda_br(valor):
    """Apresenta um valor monetário no padrão brasileiro, sem alterar o dado."""
    try:
        quantizado = Decimal(valor).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        quantizado = Decimal("0.00")
    texto = f"{quantizado:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"
