from decimal import Decimal, InvalidOperation


def quantidade_sem_decimal(valor):
    """Mostra quantidade inteira sem ,00. Fração real permanece numérica."""
    if valor is None or valor == "":
        return 0
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return 0
    integral = numero.to_integral_value()
    if numero == integral:
        return int(integral)
    return numero
