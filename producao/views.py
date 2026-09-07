from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView

from .forms import ProducaoForm
from .models import Producao

from estoque.models import (
    MovimentacaoProduto,
    MovimentacaoInsumo,
)
from estoque.services import calcular_estoque_produto


# ============================================================
# CADASTRAR PRODUÇÃO
# ============================================================

class ProducaoCreateView(LoginRequiredMixin, CreateView):

    model = Producao
    form_class = ProducaoForm
    template_name = "producao/producao_form.html"
    success_url = reverse_lazy("producao:producao_list")

    @transaction.atomic
    def form_valid(self, form):

        # ========================================================
        # SALVA A PRODUÇÃO
        # ========================================================

        self.object = form.save()

        # ========================================================
        # ENTRA PRODUTO ACABADO NO ESTOQUE
        # ========================================================

        MovimentacaoProduto.objects.create(
            produto=self.object.produto,
            tipo="ENTRADA",
            quantidade=self.object.quantidade,
            observacao=(
                f"Entrada automática referente à "
                f"produção #{self.object.id}"
            )
        )

        # ========================================================
        # CONSOME OS INSUMOS DA COMPOSIÇÃO
        # ========================================================

        composicoes = self.object.produto.composicao.select_related(
            "insumo"
        )

        for composicao in composicoes:

            quantidade_consumida = (
                composicao.quantidade *
                self.object.quantidade
            )

            # Como quantidade do insumo é inteira,
            # convertemos para int.
            quantidade_consumida = int(
                quantidade_consumida
            )

            MovimentacaoInsumo.objects.create(
                insumo=composicao.insumo,
                tipo="SAIDA",
                quantidade=quantidade_consumida,
                observacao=(
                    f"Consumo automático referente à "
                    f"produção #{self.object.id}"
                )
            )

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

class ProducaoListView(LoginRequiredMixin, ListView):

    model = Producao
    template_name = "producao/producao_list.html"
    context_object_name = "producoes"

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        # ========================================================
        # DATA/HORA ATUAL
        # ========================================================

        agora = timezone.localtime()
        hoje = agora.date()

        # ========================================================
        # HOJE
        # ========================================================

        inicio_hoje = timezone.make_aware(
            datetime.combine(
                hoje,
                time.min
            )
        )

        fim_hoje = inicio_hoje + timedelta(days=1)

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

        # ========================================================
        # SEMANA ATUAL
        # ========================================================

        inicio_semana_data = (
            hoje - timedelta(days=hoje.weekday())
        )

        inicio_semana = timezone.make_aware(
            datetime.combine(
                inicio_semana_data,
                time.min
            )
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

        # ========================================================
        # MÊS ATUAL
        # ========================================================

        inicio_mes_data = hoje.replace(day=1)

        inicio_mes = timezone.make_aware(
            datetime.combine(
                inicio_mes_data,
                time.min
            )
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

        estoque_3kg = calcular_estoque_produto(peso_kg=3)
        estoque_5kg = calcular_estoque_produto(peso_kg=5)

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