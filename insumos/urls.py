from django.urls import path

from .views import CriarInsumoView, EditarInsumoView, ListaInsumosView

app_name = "insumos"

urlpatterns = [
    path("", ListaInsumosView.as_view(), name="lista_insumos"),
    path("cadastrar/", CriarInsumoView.as_view(), name="cadastrar_insumo"),
    path("<int:pk>/editar/", EditarInsumoView.as_view(), name="editar_insumo"),
]
