from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce

JANELA_VENCIMENTO_DIAS = 7
CENTAVO = Decimal("0.01")
CEM = Decimal("100")
ZERO = Decimal("0.00")
ZERO_AGG = Value(ZERO, output_field=DecimalField(max_digits=12, decimal_places=2))


def quantize(valor):
    if valor is None:
        return ZERO
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def agregar(queryset):
    dados = queryset.aggregate(
        quantidade=Count("id"),
        total=Coalesce(Sum("valor"), ZERO_AGG),
    )
    return int(dados["quantidade"] or 0), quantize(dados["total"])


def variacao(atual, anterior):
    if anterior <= 0:
        return None
    percentual = ((atual - anterior) / anterior) * CEM
    return percentual.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percentual(parte, total):
    if total <= 0:
        return ZERO
    return ((parte / total) * CEM).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def chart_valores(labels, values, tipo="bar", label="Pago (R$)", legenda=False):
    return {
        "type": tipo,
        "label": label,
        "labels": labels,
        "values": [float(valor) for valor in values],
        "currency": True,
        "showLegend": legenda,
    }
