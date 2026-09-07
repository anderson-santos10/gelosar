from django.urls import path
from .views import DashboardClienteView, ListaClientesView, CriarClienteView


urlpatterns = [
    path('clientes/', ListaClientesView.as_view(), name='lista_clientes'),
    path('clientes/cadastrar/', CriarClienteView.as_view(), name='cadastrar_cliente'),
    path('cliente/<int:pk>/dashboard/', DashboardClienteView.as_view(), name='dashboard_cliente'),

]