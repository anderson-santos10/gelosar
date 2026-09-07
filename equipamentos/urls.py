from django.urls import path
from .views import DocumentoCreateView, DocumentoDownloadView, DocumentoIndiceView, DocumentoListView, EquipamentoCreateView, EquipamentoDeleteView, EquipamentoDetailView, EquipamentoListView, EquipamentoUpdateView, ContratoComodatoView

app_name = "equipamentos"

urlpatterns = [
    path('', EquipamentoListView.as_view(), name='listar_equipamentos'),
    path('cadastrar/', EquipamentoCreateView.as_view(), name='cadastrar_equipamentos'),
    path('documentos/', DocumentoIndiceView.as_view(), name='indice_documentos'),
    path('documentos/<int:pk>/download/', DocumentoDownloadView.as_view(), name='download_documento'),
    path("contrato-comodato/", ContratoComodatoView.as_view(), name="contrato_comodato"),
    path('<int:pk>/upload/', DocumentoCreateView.as_view(), name='upload_documento'),
    path('<int:pk>/', EquipamentoDetailView.as_view(), name='detalhe_equipamento'),
    path('<int:pk>/editar/', EquipamentoUpdateView.as_view(), name='editar_equipamento'),
    path('<int:pk>/excluir/', EquipamentoDeleteView.as_view(), name='excluir_equipamento'),
    path('<int:pk>/documentos/', DocumentoListView.as_view(), name='listar_documentos'),
]
