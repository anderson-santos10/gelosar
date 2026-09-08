from django.db import transaction

from core.auditoria import atribuir_criado_por
from estoque.models import MovimentacaoInsumo, MovimentacaoProduto
from estoque.services import quantidade_para_movimento


class ProdutoSemComposicao(Exception):
    """Produto sem BOM: produção não gera estoque."""


def registrar_producao(form, criado_por=None):
    """
    Persiste a produção e aplica a regra já existente de estoque:

    * ENTRADA do produto acabado (independente de ESTOQUE_DATA_CORTE);
    * SAIDA de cada insumo da composição, na mesma transação.

    Não altera quantidade, composição nem fórmula de saldo.
    criado_por vem da view (request.user), não do formulário HTML.
    """
    produto = form.cleaned_data["produto"]
    if not produto.composicao.exists():
        raise ProdutoSemComposicao()

    with transaction.atomic():
        producao = form.save(commit=False)
        atribuir_criado_por(producao, criado_por)
        producao.save()

        MovimentacaoProduto.objects.create(
            produto=producao.produto,
            tipo="ENTRADA",
            quantidade=producao.quantidade,
            observacao=(
                f"Entrada automática referente à "
                f"produção #{producao.id}"
            ),
        )

        composicoes = producao.produto.composicao.select_related("insumo")
        for composicao in composicoes:
            quantidade_consumida = quantidade_para_movimento(
                composicao.quantidade * producao.quantidade
            )
            MovimentacaoInsumo.objects.create(
                insumo=composicao.insumo,
                tipo="SAIDA",
                quantidade=quantidade_consumida,
                observacao=(
                    f"Consumo automático referente à "
                    f"produção #{producao.id}"
                ),
            )

    return producao
