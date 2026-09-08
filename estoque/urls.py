from django.urls import path

from .views import AjusteProdutoView, EntradaInsumoView, EstoqueView

app_name = "estoque"

urlpatterns = [
    path("", EstoqueView.as_view(), name="estoque"),
    path("entrada-insumo/", EntradaInsumoView.as_view(), name="entrada_insumo"),
    path("ajuste/", AjusteProdutoView.as_view(), name="ajuste_produto"),
]
