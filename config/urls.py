from django.contrib import admin
from django.urls import include, path

from accounts.views import home


urlpatterns = [

    path(
        '',
        home,
        name='home'
    ),

    path(
        'admin/',
        admin.site.urls
    ),

    path(
        'dashboard/',
        include('core.urls')
    ),

    path(
        '',
        include('accounts.urls')
    ),

    path(
        'equipamentos/',
        include('equipamentos.urls')
    ),

    path(
        'producao/',
        include('producao.urls')
    ),

    path(
        '',
        include('clientes.urls')
    ),

    path(
        'vendas/',
        include('vendas.urls')
    ),

    path(
        'estoque/',
        include('estoque.urls')
    ),

    path(
        'produtos/',
        include('produtos.urls')
    ),

    path(
        'insumos/',
        include('insumos.urls')
    ),

]
