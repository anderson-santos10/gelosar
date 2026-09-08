from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView

from accounts.authz import ModulePermissionRequiredMixin

from insumos.models import Insumo
from .models import MovimentacaoInsumo, MovimentacaoProduto
from .forms import AjusteProdutoForm, EntradaInsumoForm
from .services import calcular_estoques_insumos, calcular_estoques_produto_por_peso

class EstoqueView(LoginRequiredMixin, ModulePermissionRequiredMixin, TemplateView):

    permission_required = "estoque.view_movimentacaoproduto"

    template_name = "estoque/estoque.html"

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        # ============================================================
        # MOVIMENTAÇÕES
        # ============================================================

        movimentacoes = (
            MovimentacaoProduto.objects
            .select_related("produto")
            .order_by("-criado_em")
        )

        # ============================================================
        # ESTOQUE OFICIAL (ENTRADA - SAIDA + AJUSTE)
        # ============================================================

        estoques = calcular_estoques_produto_por_peso(5, 3)
        estoque_5kg_sacos = estoques[5]
        estoque_3kg_sacos = estoques[3]

        # ============================================================
        # PESO TOTAL
        # ============================================================

        estoque_5kg_kg = estoque_5kg_sacos * 5
        estoque_3kg_kg = estoque_3kg_sacos * 3

        total_estoque_gelo_sacos = (
            estoque_5kg_sacos +
            estoque_3kg_sacos
        )

        total_estoque_gelo_kg = (
            estoque_5kg_kg +
            estoque_3kg_kg
        )

        # ============================================================
        # TOTAL DE MOVIMENTAÇÕES
        # ============================================================

        total_entradas = (
            MovimentacaoProduto.objects.filter(
                tipo="ENTRADA"
            ).count()
        )

        total_saidas = (
            MovimentacaoProduto.objects.filter(
                tipo="SAIDA"
            ).count()
        )

        total_ajustes = (
            MovimentacaoProduto.objects.filter(
                tipo="AJUSTE"
            ).count()
        )

        # ============================================================
        # CONTEXTO PARA O TEMPLATE
        # ============================================================

        context["estoque_5kg_sacos"] = estoque_5kg_sacos
        context["estoque_3kg_sacos"] = estoque_3kg_sacos

        context["estoque_5kg_kg"] = estoque_5kg_kg
        context["estoque_3kg_kg"] = estoque_3kg_kg

        context["total_estoque_gelo_sacos"] = (
            total_estoque_gelo_sacos
        )

        context["total_estoque_gelo_kg"] = (
            total_estoque_gelo_kg
        )

        context["total_entradas"] = total_entradas
        context["total_saidas"] = total_saidas
        context["total_ajustes"] = total_ajustes

        context["movimentacoes"] = movimentacoes[:20]

        insumos = list(Insumo.objects.all())
        saldos = calcular_estoques_insumos(insumos)
        saldos_insumos = [
            {"insumo": insumo, "saldo": saldos[insumo]}
            for insumo in insumos
        ]
        context["saldos_insumos"] = saldos_insumos

        return context
    
class EntradaInsumoView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):

    permission_required = "estoque.add_movimentacaoinsumo"

    model = MovimentacaoInsumo

    form_class = EntradaInsumoForm

    template_name = "estoque/entrada_insumo.html"

    success_url = reverse_lazy("estoque:estoque")

    def form_valid(self, form):

        response = super().form_valid(form)

        messages.success(
            self.request,
            (
                f"Entrada de {self.object.quantidade} "
                f"{self.object.insumo.unidade} "
                f"de {self.object.insumo.nome} "
                f"registrada com sucesso."
            )
        )

        return response


class AjusteProdutoView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):

    permission_required = "estoque.add_movimentacaoproduto"

    model = MovimentacaoProduto
    form_class = AjusteProdutoForm
    template_name = "estoque/ajuste_produto.html"
    success_url = reverse_lazy("estoque:estoque")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            (
                f"Ajuste de +{self.object.quantidade} sacos "
                f"de {self.object.produto.nome} registrado."
            ),
        )
        return response