from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.authz import ModulePermissionRequiredMixin

from .forms import InsumoForm
from .models import Insumo


class ListaInsumosView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "insumos.view_insumo"
    model = Insumo
    template_name = "insumos/lista_insumos.html"
    context_object_name = "insumos"


class CriarInsumoView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "insumos.add_insumo"
    model = Insumo
    form_class = InsumoForm
    template_name = "insumos/insumo_form.html"
    success_url = reverse_lazy("insumos:lista_insumos")


class EditarInsumoView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "insumos.change_insumo"
    model = Insumo
    form_class = InsumoForm
    template_name = "insumos/insumo_form.html"
    success_url = reverse_lazy("insumos:lista_insumos")
