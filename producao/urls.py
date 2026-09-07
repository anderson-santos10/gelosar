from django.urls import path
from .views import ProducaoCreateView, ProducaoListView

app_name = "producao"

urlpatterns = [
    path("nova/",ProducaoCreateView.as_view(), name="new_producao"),
    path("producao/",ProducaoListView.as_view(),name="producao_list"),
    
]