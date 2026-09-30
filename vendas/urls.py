from django.urls import path

from .views import (
    cadastrar_pedido,
    confirmar_entrega_pedido,
    detalhe_pedido,
    detalhe_venda,
    historico_pedidos,
    nova_venda,
    pedidos_abertos,
)


app_name = 'vendas'


urlpatterns = [

    path(
        'novo/',
        nova_venda,
        name='novo_pedido'
    ),

    path(
        'pedidos/novo/',
        cadastrar_pedido,
        name='cadastrar_pedido',
    ),

    path(
        'pedidos/historico/',
        historico_pedidos,
        name='historico_pedidos',
    ),

    path(
        'pedidos/<int:pk>/entregar/',
        confirmar_entrega_pedido,
        name='entregar_pedido',
    ),

    path(
        'pedidos/<int:pk>/',
        detalhe_pedido,
        name='detalhe_pedido',
    ),

    path(
        'pedidos/',
        pedidos_abertos,
        name='pedidos_abertos',
    ),

    path(
        '<int:pk>/',
        detalhe_venda,
        name='detalhe_venda'
    ),

]
