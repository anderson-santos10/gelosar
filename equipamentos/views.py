from pathlib import Path

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DeleteView, DetailView, ListView, CreateView, UpdateView, TemplateView

from .models import Equipamento, DocumentoEquipamento
from .forms import DocumentoEquipamentoForm



class EquipamentoCreateView(LoginRequiredMixin, CreateView):
    model = Equipamento
    fields = [
        'nome',
        'tipo',
        'cliente',
        'fabricante',
        'numero_serie',
        'valor_compra',
        'data_compra',
        'garantia_meses',
        'localizacao',
        'status',
        'observacoes',
    ]

    template_name = 'equipamentos/cadastrar_equipamentos.html'
    success_url = reverse_lazy('equipamentos:listar_equipamentos')
    

class EquipamentoListView(LoginRequiredMixin, ListView):
    model = Equipamento
    template_name = 'equipamentos/listar_equipamentos.html'
    context_object_name = 'equipamentos'
    ordering = ['-id']  
    
class DocumentoCreateView(LoginRequiredMixin, CreateView):
    model = DocumentoEquipamento
    form_class = DocumentoEquipamentoForm
    template_name = 'equipamentos/upload_documento.html'

    def get_equipamento(self):
        return get_object_or_404(Equipamento, id=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['equipamento'] = self.get_equipamento()
        return context

    def form_valid(self, form):
        form.instance.equipamento = self.get_equipamento()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'equipamentos:listar_documentos',
            kwargs={'pk': self.object.equipamento.id},
        )
    
class ContratoComodatoView(LoginRequiredMixin, TemplateView):
    template_name = "equipamentos/contrato_comodato.html"
    
    
class EquipamentoDetailView(LoginRequiredMixin, DetailView):
    model = Equipamento
    template_name = 'equipamentos/equipamento_detail.html'
    context_object_name = 'equipamento'
    
    
class EquipamentoUpdateView(LoginRequiredMixin, UpdateView):
    model = Equipamento
    fields = [
        'nome',
        'tipo',
        'cliente',
        'fabricante',
        'numero_serie',
        'valor_compra',
        'data_compra',
        'garantia_meses',
        'localizacao',
        'status',
        'observacoes',
    ]

    template_name = 'equipamentos/editar_equipamento.html'
    success_url = reverse_lazy('equipamentos:listar_equipamentos')
    context_object_name = 'equipamento'
    
class EquipamentoDeleteView(LoginRequiredMixin, DeleteView):
    model = Equipamento
    template_name = 'equipamentos/excluir_equipamento.html'
    success_url = reverse_lazy('equipamentos:listar_equipamentos')
    
    
class DocumentoListView(LoginRequiredMixin, ListView):
    model = DocumentoEquipamento
    template_name = 'equipamentos/documentos_list.html'
    context_object_name = 'documentos'

    def get_equipamento(self):
        return get_object_or_404(Equipamento, id=self.kwargs['pk'])

    def get_queryset(self):
        return DocumentoEquipamento.objects.filter(
            equipamento=self.get_equipamento()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['equipamento'] = self.get_equipamento()
        return context


class DocumentoIndiceView(LoginRequiredMixin, ListView):
    model = DocumentoEquipamento
    template_name = 'equipamentos/documentos_indice.html'
    context_object_name = 'documentos'

    def get_queryset(self):
        return (
            DocumentoEquipamento.objects
            .select_related('equipamento', 'equipamento__cliente')
            .order_by('-data_upload')
        )


class DocumentoDownloadView(LoginRequiredMixin, View):

    def get(self, request, pk):
        documento = get_object_or_404(DocumentoEquipamento, pk=pk)
        arquivo = documento.arquivo

        if not arquivo:
            raise Http404("Documento sem arquivo.")

        try:
            if not arquivo.storage.exists(arquivo.name):
                raise Http404("Arquivo não encontrado.")
            handle = arquivo.open("rb")
        except Http404:
            raise
        except Exception:
            raise Http404("Arquivo não encontrado.")

        nome = Path(arquivo.name).name
        return FileResponse(
            handle,
            as_attachment=False,
            filename=nome,
        )
