from django.urls import path

from .views import CriarProdutoView, EditarProdutoView, ListaProdutosView

app_name = "produtos"

urlpatterns = [
    path("", ListaProdutosView.as_view(), name="lista_produtos"),
    path("cadastrar/", CriarProdutoView.as_view(), name="cadastrar_produto"),
    path("<int:pk>/editar/", EditarProdutoView.as_view(), name="editar_produto"),
]
