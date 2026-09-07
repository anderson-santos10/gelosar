from django.contrib import admin
from .models import Produto, ComposicaoProduto


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "nome",
        "peso_kg",
        "preco_venda",
        "estoque_minimo",
        "ativo",
    )

    list_filter = (
        "ativo",
        "peso_kg",
    )

    search_fields = (
        "nome",
    )


@admin.register(ComposicaoProduto)
class ComposicaoProdutoAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "produto",
        "insumo",
        "quantidade",
    )

    list_filter = (
        "produto",
        "insumo",
    )