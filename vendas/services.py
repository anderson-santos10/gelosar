from django.db import transaction
from django.utils import timezone

from core.auditoria import atribuir_criado_por
from estoque.services import registrar_saidas_venda

from .models import ItemPedido, ItemVenda, Pedido, Venda


class PedidoNaoAberto(Exception):
    def __init__(self, mensagem):
        self.mensagem = mensagem
        super().__init__(mensagem)


def entregar_pedido(pedido_id, usuario):
    """Transforma um pedido aberto em venda e baixa o estoque na mesma transação.

    Se qualquer etapa falhar, nada é gravado e o pedido continua aberto.
    """
    with transaction.atomic():
        pedido = (
            Pedido.objects.select_for_update()
            .select_related("cliente")
            .get(pk=pedido_id)
        )
        if pedido.status == Pedido.STATUS_ENTREGUE or pedido.venda_id:
            raise PedidoNaoAberto("Este pedido já foi entregue.")
        if pedido.status != Pedido.STATUS_ABERTO:
            raise PedidoNaoAberto("Este pedido não está aberto.")

        venda = Venda(
            cliente=pedido.cliente,
            observacoes=pedido.observacoes,
        )
        atribuir_criado_por(venda, usuario)
        venda.save()

        itens = ItemPedido.objects.filter(pedido=pedido).select_related("produto")
        for item in itens:
            item_venda = ItemVenda(
                venda=venda,
                produto=item.produto,
                quantidade=item.quantidade,
            )
            item_venda.save()
            ItemVenda.objects.filter(pk=item_venda.pk).update(
                preco_unitario=item.preco_unitario
            )

        registrar_saidas_venda(venda)

        pedido.status = Pedido.STATUS_ENTREGUE
        pedido.entregue_em = timezone.now()
        pedido.entregue_por = usuario
        pedido.venda = venda
        pedido.full_clean()
        pedido.save()
        return pedido
