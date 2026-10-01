from collections import OrderedDict
from decimal import Decimal

from core.numeros import quantidade_sem_decimal


def agrupar_compras(vendas):
    """Agrupa vendas do mesmo cliente no mesmo dia, sem alterar os registros."""
    por_chave = OrderedDict()
    for venda in vendas:
        chave = (venda.cliente_id, venda.data)
        por_chave.setdefault(chave, []).append(venda)

    grupos = []
    for (cliente_id, data), vendas_dia in por_chave.items():
        produtos = OrderedDict()
        for venda in vendas_dia:
            for item in venda.itens.all():
                atual = produtos.get(item.produto_id)
                subtotal = Decimal(item.subtotal)
                quantidade = Decimal(item.quantidade)
                if atual is None:
                    produtos[item.produto_id] = {
                        "produto": item.produto.nome,
                        "quantidade": quantidade,
                        "subtotal": subtotal,
                    }
                else:
                    atual["quantidade"] += quantidade
                    atual["subtotal"] += subtotal
        itens = [
            {
                "produto": item["produto"],
                "quantidade": quantidade_sem_decimal(item["quantidade"]),
                "subtotal": item["subtotal"],
            }
            for item in produtos.values()
        ]
        quantidade_dia = sum(
            (Decimal(item["quantidade"]) for item in itens),
            Decimal("0"),
        )
        total = sum((item["subtotal"] for item in itens), Decimal("0"))
        grupos.append(
            {
                "cliente_id": cliente_id,
                "cliente": vendas_dia[0].cliente,
                "data": data,
                "itens": itens,
                "quantidade": quantidade_sem_decimal(quantidade_dia),
                "total": total,
                "vendas": vendas_dia,
            }
        )
    grupos.sort(key=lambda grupo: (grupo["data"], grupo["cliente_id"]), reverse=True)
    return grupos
