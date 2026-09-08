from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.authz import ModulePermissionRequiredMixin

from .forms import ProdutoForm
from .models import Produto


class ListaProdutosView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "produtos.view_produto"
    model = Produto
    template_name = "produtos/lista_produtos.html"
    context_object_name = "produtos"


class CriarProdutoView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "produtos.add_produto"
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista_produtos")


class EditarProdutoView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "produtos.change_produto"
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista_produtos")
