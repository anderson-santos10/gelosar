from pathlib import Path

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.text import get_valid_filename
from django.views import View
from django.views.generic import DeleteView, DetailView, ListView, CreateView, UpdateView

from accounts.authz import ModulePermissionRequiredMixin

from .models import ContratoComodato, Equipamento, DocumentoEquipamento
from .forms import ContratoComodatoForm, DocumentoEquipamentoForm



class EquipamentoCreateView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "equipamentos.add_equipamento"
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
    

class EquipamentoListView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "equipamentos.view_equipamento"
    model = Equipamento
    template_name = 'equipamentos/listar_equipamentos.html'
    context_object_name = 'equipamentos'
    ordering = ['-id']

    def get_queryset(self):
        return super().get_queryset().select_related("cliente")
    
class DocumentoCreateView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "equipamentos.add_documentoequipamento"
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
    
class ContratoComodatoListView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "equipamentos.view_contratocomodato"
    model = ContratoComodato
    template_name = "equipamentos/contrato_comodato_list.html"
    context_object_name = "contratos"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("cliente", "equipamento")
        )


class ContratoComodatoCreateView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "equipamentos.add_contratocomodato"
    model = ContratoComodato
    form_class = ContratoComodatoForm
    template_name = "equipamentos/contrato_comodato_form.html"

    def get_success_url(self):
        return reverse(
            "equipamentos:contrato_comodato_detalhe",
            kwargs={"pk": self.object.pk},
        )


class ContratoComodatoDetailView(LoginRequiredMixin, ModulePermissionRequiredMixin, DetailView):
    permission_required = "equipamentos.view_contratocomodato"
    model = ContratoComodato
    template_name = "equipamentos/contrato_comodato.html"
    context_object_name = "contrato"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("cliente", "equipamento")
        )


class ContratoComodatoUpdateView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "equipamentos.change_contratocomodato"
    model = ContratoComodato
    form_class = ContratoComodatoForm
    template_name = "equipamentos/contrato_comodato_form.html"

    def get_success_url(self):
        return reverse(
            "equipamentos:contrato_comodato_detalhe",
            kwargs={"pk": self.object.pk},
        )
    
class EquipamentoDetailView(LoginRequiredMixin, ModulePermissionRequiredMixin, DetailView):
    permission_required = "equipamentos.view_equipamento"
    model = Equipamento
    template_name = 'equipamentos/equipamento_detail.html'
    context_object_name = 'equipamento'
    
    
class EquipamentoUpdateView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "equipamentos.change_equipamento"
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
    
class EquipamentoDeleteView(LoginRequiredMixin, ModulePermissionRequiredMixin, DeleteView):
    permission_required = "equipamentos.delete_equipamento"
    model = Equipamento
    template_name = 'equipamentos/excluir_equipamento.html'
    success_url = reverse_lazy('equipamentos:listar_equipamentos')
    
    
class DocumentoListView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "equipamentos.view_equipamento"
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


class DocumentoIndiceView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "equipamentos.view_equipamento"
    model = DocumentoEquipamento
    template_name = 'equipamentos/documentos_indice.html'
    context_object_name = 'documentos'

    def get_queryset(self):
        return (
            DocumentoEquipamento.objects
            .select_related('equipamento', 'equipamento__cliente')
            .order_by('-data_upload')
        )


class DocumentoDownloadView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = "equipamentos.view_equipamento"

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

        nome_bruto = Path(arquivo.name).name.replace("\r", "").replace("\n", "")
        nome = get_valid_filename(nome_bruto) or "documento"
        response = FileResponse(
            handle,
            as_attachment=True,
            filename=nome,
            content_type="application/octet-stream",
        )
        response["Content-Type"] = "application/octet-stream"
        response["X-Content-Type-Options"] = "nosniff"
        return response
