from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.utils import timezone
from django.views.generic import TemplateView

from equipamentos.models import Equipamento
from estoque.services import (
    calcular_estoque_insumo,
    calcular_estoque_produto,
)
from producao.models import Producao

from .charts import producao_por_dia, vendas_por_dia


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        hoje = timezone.localdate()
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        inicio_mes = hoje.replace(day=1)

        # ============================================================
        # EQUIPAMENTOS
        # ============================================================

        equipamentos = Equipamento.objects.all()

        context["total_equipamentos"] = equipamentos.count()
        context["ativos"] = equipamentos.filter(status="ativo").count()
        context["parados"] = equipamentos.filter(status="parado").count()
        context["manutencao"] = equipamentos.filter(
            status="manutencao"
        ).count()
        context["inativos"] = equipamentos.filter(
            status="inativo"
        ).count()

        # ============================================================
        # PRODUÇÃO
        # ============================================================

        producoes = Producao.objects.all()

        producao_hoje = (
            producoes.filter(
                data_hora__date=hoje
            )
            .aggregate(total=Sum("quantidade"))["total"]
            or 0
        )

        producao_semana = (
            producoes.filter(
                data_hora__date__gte=inicio_semana,
                data_hora__date__lte=hoje,
            )
            .aggregate(total=Sum("quantidade"))["total"]
            or 0
        )

        producao_mes = (
            producoes.filter(
                data_hora__date__gte=inicio_mes,
                data_hora__date__lte=hoje,
            )
            .aggregate(total=Sum("quantidade"))["total"]
            or 0
        )

        context["producao_hoje"] = producao_hoje
        context["producao_semana"] = producao_semana
        context["producao_mes"] = producao_mes

        # ============================================================
        # ESTOQUE DE GELO
        # ============================================================

        estoque_5kg = calcular_estoque_produto(peso_kg=5)
        estoque_3kg = calcular_estoque_produto(peso_kg=3)

        total_estoque_gelo = estoque_5kg + estoque_3kg

        context["estoque_5kg_sacos"] = estoque_5kg
        context["estoque_3kg_sacos"] = estoque_3kg
        context["total_estoque_gelo_sacos"] = total_estoque_gelo

        # ============================================================
        # ESTOQUE DE EMBALAGENS
        # ============================================================

        estoque_embalagem_5kg = calcular_estoque_insumo(
            nome="Embalagem Gelo 5k"
        )

        estoque_embalagem_3kg = calcular_estoque_insumo(
            nome="Embalagem Gelo 3k"
        )

        total_insumos = (
            estoque_embalagem_5kg
            + estoque_embalagem_3kg
        )

        context["insumos_5kg_unidades"] = estoque_embalagem_5kg
        context["insumos_3kg_unidades"] = estoque_embalagem_3kg
        context["total_insumos_unidades"] = total_insumos

        context["chart_vendas"] = vendas_por_dia()
        context["chart_producao"] = producao_por_dia()
        context["chart_estoque"] = {
            "type": "bar",
            "label": "Sacos",
            "labels": ["Gelo 5kg", "Gelo 3kg"],
            "values": [estoque_5kg, estoque_3kg],
        }

        return context