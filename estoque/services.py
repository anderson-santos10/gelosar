from decimal import Decimal

from django.db.models import Case, IntegerField, Sum, Value, When
from django.db.models.functions import Coalesce

from .data_corte import get_data_corte
from .models import MovimentacaoInsumo, MovimentacaoProduto

# Tipos oficiais atuais de MovimentacaoProduto / MovimentacaoInsumo.
TIPO_ENTRADA = "ENTRADA"
TIPO_SAIDA = "SAIDA"
TIPO_AJUSTE = "AJUSTE"

# AJUSTE no model atual usa PositiveIntegerField: só acréscimo.
# Inventário abaixo do livro (ajuste negativo) fica para etapa posterior,
# sem migration nesta etapa.


def calcular_saldo_oficial(entrada, saida, ajuste):
    """
    Saldo oficial do livro:

        ESTOQUE = ENTRADA - SAIDA + AJUSTE

    Não aplica max(..., 0). Saldo negativo permanece visível.
    """
    return int(entrada or 0) - int(saida or 0) + int(ajuste or 0)


def _somas_por_tipo():
    zero = Value(0, output_field=IntegerField())
    return {
        "entrada": Coalesce(
            Sum(
                Case(
                    When(tipo=TIPO_ENTRADA, then="quantidade"),
                    default=zero,
                    output_field=IntegerField(),
                )
            ),
            zero,
        ),
        "saida": Coalesce(
            Sum(
                Case(
                    When(tipo=TIPO_SAIDA, then="quantidade"),
                    default=zero,
                    output_field=IntegerField(),
                )
            ),
            zero,
        ),
        "ajuste": Coalesce(
            Sum(
                Case(
                    When(tipo=TIPO_AJUSTE, then="quantidade"),
                    default=zero,
                    output_field=IntegerField(),
                )
            ),
            zero,
        ),
    }


def _saldo_de_queryset(queryset):
    totais = queryset.aggregate(**_somas_por_tipo())
    return calcular_saldo_oficial(
        totais["entrada"],
        totais["saida"],
        totais["ajuste"],
    )


def _saldos_agrupados(queryset, chave):
    rows = queryset.values(chave).annotate(**_somas_por_tipo())
    return {
        row[chave]: calcular_saldo_oficial(
            row["entrada"],
            row["saida"],
            row["ajuste"],
        )
        for row in rows
    }


def calcular_estoque_produto(*, produto=None, peso_kg=None):
    """
    Saldo de produto acabado a partir de MovimentacaoProduto.

    Informe produto ou peso_kg (ex.: 3 ou 5).
    """
    if produto is None and peso_kg is None:
        raise ValueError("Informe produto ou peso_kg.")
    if produto is not None and peso_kg is not None:
        raise ValueError("Informe somente produto ou somente peso_kg.")

    movimentos = MovimentacaoProduto.objects.all()
    if produto is not None:
        movimentos = movimentos.filter(produto=produto)
    else:
        movimentos = movimentos.filter(produto__peso_kg=peso_kg)

    return _saldo_de_queryset(movimentos)


def calcular_estoques_produto_por_peso(*pesos):
    """Um único aggregate agrupado por peso_kg. Pesos ausentes → 0."""
    pesos_int = [int(p) for p in pesos]
    agrupado = _saldos_agrupados(
        MovimentacaoProduto.objects.filter(produto__peso_kg__in=pesos_int),
        "produto__peso_kg",
    )
    resultado = {peso: 0 for peso in pesos_int}
    for peso, saldo in agrupado.items():
        resultado[int(peso)] = saldo
    return resultado


def calcular_estoque_insumo(*, insumo=None, nome=None):
    """
    Saldo de insumo a partir de MovimentacaoInsumo.

    Mesma fórmula oficial, sem mascarar negativo.
    Informe insumo ou nome.
    """
    if insumo is None and nome is None:
        raise ValueError("Informe insumo ou nome.")
    if insumo is not None and nome is not None:
        raise ValueError("Informe somente insumo ou somente nome.")

    movimentos = MovimentacaoInsumo.objects.all()
    if insumo is not None:
        movimentos = movimentos.filter(insumo=insumo)
    else:
        movimentos = movimentos.filter(insumo__nome=nome)

    return _saldo_de_queryset(movimentos)


def calcular_estoques_insumos(insumos):
    """Saldos de vários insumos em uma consulta agrupada."""
    insumos = list(insumos)
    if not insumos:
        return {}
    ids = [insumo.pk for insumo in insumos]
    agrupado = _saldos_agrupados(
        MovimentacaoInsumo.objects.filter(insumo_id__in=ids),
        "insumo_id",
    )
    return {
        insumo: agrupado.get(insumo.pk, 0)
        for insumo in insumos
    }


def calcular_estoques_insumo_por_nome(*nomes):
    """Um aggregate agrupado por nome de insumo. Nomes ausentes → 0."""
    agrupado = _saldos_agrupados(
        MovimentacaoInsumo.objects.filter(insumo__nome__in=nomes),
        "insumo__nome",
    )
    return {nome: agrupado.get(nome, 0) for nome in nomes}


def venda_deve_gerar_saida(venda):
    """
    Decisão única de SAIDA automática de venda.

    ESTOQUE_DATA_CORTE ausente (None) → False (não gera SAIDA).
    venda.data ausente → False.
    Caso contrário → True somente se venda.data >= data de corte.

    Não faz backfill. Não é usada pela produção.
    """
    data_corte = get_data_corte()
    if data_corte is None:
        return False
    if getattr(venda, "data", None) is None:
        return False
    return venda.data >= data_corte


class QuantidadeNaoInteira(ValueError):
    """Quantidade fracionada não pode virar movimentação de estoque."""


def quantidade_para_movimento(quantidade):
    """
    Converte quantidade vendida para o livro (PositiveIntegerField).

    Aceita somente valores inteiros (ex.: 10 ou 10.00).
    Não trunca nem arredonda 10.50 → 10.
    """
    valor = Decimal(str(quantidade))
    if valor != valor.to_integral_value():
        raise QuantidadeNaoInteira(
            "A quantidade deve ser um número inteiro de sacos."
        )
    quantidade_inteira = int(valor.to_integral_value())
    if quantidade_inteira <= 0:
        raise QuantidadeNaoInteira(
            "A quantidade deve ser um número inteiro maior que zero."
        )
    return quantidade_inteira


def registrar_saidas_venda(venda):
    """
    Cria uma MovimentacaoProduto SAIDA por item persistido da venda.

    Não faz backfill: só age se for chamado na criação da venda.
    Configurar ESTOQUE_DATA_CORTE depois não cria SAIDA histórica.
    Não deve ser chamado em edição/exclusão.
    Chamada após os itens existirem: nova_venda (formset.save)
    e VendaAdmin.save_related somente na criação (change=False).
    Não bloqueia saldo insuficiente: a fórmula oficial permite saldo negativo.
    """
    if not venda_deve_gerar_saida(venda):
        return []

    criadas = []
    for item in venda.itens.select_related("produto"):
        if not item.produto_id:
            continue
        quantidade = quantidade_para_movimento(item.quantidade)
        movimento = MovimentacaoProduto.objects.create(
            produto=item.produto,
            tipo=TIPO_SAIDA,
            quantidade=quantidade,
            observacao=(
                f"Saída automática referente à venda #{venda.id}"
            ),
        )
        criadas.append(movimento)
    return criadas
