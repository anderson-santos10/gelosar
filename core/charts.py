from datetime import date, timedelta
from decimal import Decimal

from django.db.models import F, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from estoque.services import calcular_estoque_produto
from producao.models import Producao
from vendas.models import ItemVenda

DIAS_GRAFICO = 7
MESES_GRAFICO = 6


def _primeiro_dia_meses_atras(referencia, meses_atras):
    mes = referencia.month - meses_atras
    ano = referencia.year
    while mes <= 0:
        mes += 12
        ano -= 1
    return date(ano, mes, 1)


def vendas_por_dia(dias=DIAS_GRAFICO):
    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=dias - 1)
    rows = (
        ItemVenda.objects.filter(
            venda__data__gte=inicio,
            venda__data__lte=hoje,
        )
        .values("venda__data")
        .annotate(total=Sum(F("quantidade") * F("preco_unitario")))
        .order_by("venda__data")
    )
    por_dia = {
        row["venda__data"]: row["total"] or Decimal("0")
        for row in rows
    }
    labels = []
    valores = []
    for i in range(dias):
        dia = inicio + timedelta(days=i)
        labels.append(dia.strftime("%d/%m"))
        valores.append(float(por_dia.get(dia) or 0))
    return {
        "type": "bar",
        "label": "Vendas (R$)",
        "labels": labels,
        "values": valores,
        "currency": True,
    }


def producao_por_dia(dias=DIAS_GRAFICO):
    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=dias - 1)
    rows = (
        Producao.objects.filter(
            data_hora__date__gte=inicio,
            data_hora__date__lte=hoje,
        )
        .annotate(dia=TruncDate("data_hora"))
        .values("dia", "produto__peso_kg")
        .annotate(total=Sum("quantidade"))
        .order_by("dia")
    )
    lookup = {}
    for row in rows:
        dia = row["dia"]
        if hasattr(dia, "date"):
            dia = dia.date()
        peso = row["produto__peso_kg"]
        bucket = int(peso) if peso is not None else None
        lookup[(dia, bucket)] = (lookup.get((dia, bucket), 0) + (row["total"] or 0))

    labels = []
    serie_3 = []
    serie_5 = []
    for i in range(dias):
        dia = inicio + timedelta(days=i)
        labels.append(dia.strftime("%d/%m"))
        serie_3.append(int(lookup.get((dia, 3), 0)))
        serie_5.append(int(lookup.get((dia, 5), 0)))

    return {
        "type": "bar",
        "labels": labels,
        "showLegend": True,
        "datasets": [
            {"label": "Gelo 3kg", "data": serie_3},
            {"label": "Gelo 5kg", "data": serie_5},
        ],
    }


def estoque_atual_gelo():
    return {
        "type": "bar",
        "label": "Sacos",
        "labels": ["Gelo 5kg", "Gelo 3kg"],
        "values": [
            calcular_estoque_produto(peso_kg=5),
            calcular_estoque_produto(peso_kg=3),
        ],
    }


def compras_cliente_por_mes(cliente, meses=MESES_GRAFICO):
    hoje = timezone.localdate()
    inicio = _primeiro_dia_meses_atras(hoje.replace(day=1), meses - 1)
    rows = (
        ItemVenda.objects.filter(
            venda__cliente=cliente,
            venda__data__gte=inicio,
            venda__data__lte=hoje,
        )
        .annotate(mes=TruncMonth("venda__data"))
        .values("mes")
        .annotate(total=Sum(F("quantidade") * F("preco_unitario")))
        .order_by("mes")
    )
    por_mes = {}
    for row in rows:
        mes = row["mes"]
        if hasattr(mes, "date"):
            mes = mes.date()
        chave = date(mes.year, mes.month, 1)
        por_mes[chave] = row["total"] or Decimal("0")

    labels = []
    valores = []
    for i in range(meses):
        mes = _primeiro_dia_meses_atras(hoje.replace(day=1), meses - 1 - i)
        labels.append(mes.strftime("%m/%Y"))
        valores.append(float(por_mes.get(mes) or 0))
    return {
        "type": "bar",
        "label": "Compras (R$)",
        "labels": labels,
        "values": valores,
        "currency": True,
    }


def mix_produtos_cliente(produtos):
    labels = list(produtos.keys())
    valores = [float(quantidade) for quantidade in produtos.values()]
    return {
        "type": "bar",
        "label": "Sacos",
        "labels": labels,
        "values": valores,
    }
