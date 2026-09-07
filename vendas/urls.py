from django.urls import path

from .views import detalhe_venda, nova_venda


app_name = 'vendas'


urlpatterns = [

    path(
        'novo/',
        nova_venda,
        name='novo_pedido'
    ),
    
    path(
        '<int:pk>/',
        detalhe_venda,
        name='detalhe_venda'
    ),

]