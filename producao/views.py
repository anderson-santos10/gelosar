from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from accounts.authz import ModulePermissionRequiredMixin
from core.periodo import dia_local_atual, intervalo_dia_local
from estoque.services import (
    QuantidadeNaoInteira,
    calcular_estoques_produto_por_peso,
)

from .forms import ProducaoForm
from .models import Producao
from .services import ProdutoSemComposicao, registrar_producao


# ============================================================
# CADASTRAR PRODUÇÃO
# ============================================================

class ProducaoCreateView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):

    permission_required = "producao.add_producao"

    model = Producao
    form_class = ProducaoForm
    template_name = "producao/producao_form.html"
    success_url = reverse_lazy("producao:producao_list")

    def form_valid(self, form):

        try:
            self.object = registrar_producao(
                form,
                criado_por=self.request.user,
            )
        except ProdutoSemComposicao:
            form.add_error(
                "produto",
                (
                    "Não é possível registrar produção: o produto "
                    "não possui composição de insumos. "
                    "Nenhum estoque foi gerado."
                ),
            )
            return self.form_invalid(form)
        except QuantidadeNaoInteira:
            form.add_error(
                None,
                (
                    "A produção não foi registrada porque o consumo "
                    "de insumo não resulta em quantidade inteira "
                    "maior que zero."
                ),
            )
            return self.form_invalid(form)

        # ========================================================
        # MENSAGEM
        # ========================================================

        messages.success(
            self.request,
            (
                f"Produção de "
                f"{self.object.quantidade} sacos "
                f"de {self.object.produto.nome} "
                f"registrada com sucesso. "
                f"O estoque foi atualizado."
            )
        )

        return redirect(self.success_url)


# ============================================================
# LISTAGEM DE PRODUÇÕES
# ============================================================

class ProducaoListView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):

    permission_required = "producao.view_producao"

    model = Producao
    template_name = "producao/producao_list.html"
    context_object_name = "producoes"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("equipamento", "produto")
        )

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        # ========================================================
        # DATA/HORA ATUAL
        # ========================================================

        hoje = dia_local_atual()
        inicio_hoje, fim_hoje = intervalo_dia_local(hoje)
        inicio_semana_data = hoje - timedelta(days=hoje.weekday())
        inicio_semana, _ = intervalo_dia_local(inicio_semana_data)
        inicio_mes, _ = intervalo_dia_local(hoje.replace(day=1))

        producao_hoje = (
            Producao.objects
            .filter(
                data_hora__gte=inicio_hoje,
                data_hora__lt=fim_hoje
            )
            .aggregate(
                total=Sum("quantidade")
            )
            ["total"] or 0
        )

        producao_semana = (
            Producao.objects
            .filter(
                data_hora__gte=inicio_semana,
                data_hora__lt=fim_hoje
            )
            .aggregate(
                total=Sum("quantidade")
            )
            ["total"] or 0
        )

        producao_mes = (
            Producao.objects
            .filter(
                data_hora__gte=inicio_mes,
                data_hora__lt=fim_hoje
            )
            .aggregate(
                total=Sum("quantidade")
            )
            ["total"] or 0
        )

        # ========================================================
        # ESTOQUE OFICIAL (somente exibição; criação de produção inalterada)
        # ========================================================

        estoques = calcular_estoques_produto_por_peso(3, 5)
        estoque_3kg = estoques[3]
        estoque_5kg = estoques[5]

        # ========================================================
        # CONTEXTO
        # ========================================================

        context["producao_hoje"] = producao_hoje
        context["producao_semana"] = producao_semana
        context["producao_mes"] = producao_mes

        context["total_dia"] = producao_hoje

        context["total_3kg"] = estoque_3kg
        context["total_5kg"] = estoque_5kg

        context["total_estoque"] = (
            estoque_3kg +
            estoque_5kg
        )

        return context