from django.urls import path
from .views import (
    DashboardClienteView,
    ListaClientesView,
    CriarClienteView,
    EditarClienteView,
)

app_name = "clientes"

urlpatterns = [
    path('clientes/', ListaClientesView.as_view(), name='lista_clientes'),
    path('clientes/cadastrar/', CriarClienteView.as_view(), name='cadastrar_cliente'),
    path('clientes/<int:pk>/editar/', EditarClienteView.as_view(), name='editar_cliente'),
    path('cliente/<int:pk>/dashboard/', DashboardClienteView.as_view(), name='dashboard_cliente'),

]