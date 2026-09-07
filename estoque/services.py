from decimal import Decimal

from django.db.models import Sum

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


def _soma_quantidade(queryset):
    return queryset.aggregate(total=Sum("quantidade"))["total"] or 0


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

    entrada = _soma_quantidade(movimentos.filter(tipo=TIPO_ENTRADA))
    saida = _soma_quantidade(movimentos.filter(tipo=TIPO_SAIDA))
    ajuste = _soma_quantidade(movimentos.filter(tipo=TIPO_AJUSTE))
    return calcular_saldo_oficial(entrada, saida, ajuste)


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

    entrada = _soma_quantidade(movimentos.filter(tipo=TIPO_ENTRADA))
    saida = _soma_quantidade(movimentos.filter(tipo=TIPO_SAIDA))
    ajuste = _soma_quantidade(movimentos.filter(tipo=TIPO_AJUSTE))
    return calcular_saldo_oficial(entrada, saida, ajuste)


def venda_deve_gerar_saida(venda):
    """
    SAIDA automática somente se ESTOQUE_DATA_CORTE estiver definida
    e venda.data >= data de corte.
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

    Não faz backfill. Não deve ser chamado em edição/exclusão.
    Chamada única: após formset.save() em vendas.views.nova_venda.
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
