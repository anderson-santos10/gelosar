from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.views.generic import TemplateView

from equipamentos.models import Equipamento
from estoque.services import (
    calcular_estoques_insumo_por_nome,
    calcular_estoques_produto_por_peso,
)
from producao.models import Producao

from .charts import producao_por_dia, vendas_por_dia
from .periodo import dia_local_atual, intervalo_dia_local


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        hoje = dia_local_atual()
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        inicio_mes = hoje.replace(day=1)
        inicio_hoje, fim_hoje = intervalo_dia_local(hoje)
        inicio_semana_dt, _ = intervalo_dia_local(inicio_semana)
        inicio_mes_dt, _ = intervalo_dia_local(inicio_mes)

        # ============================================================
        # EQUIPAMENTOS
        # ============================================================

        equipamentos = Equipamento.objects.all()

        context["total_equipamentos"] = equipamentos.count()
        context["ativos"] = equipamentos.filter(status="ativo").count()
        context["manutencao"] = equipamentos.filter(
            status="manutencao"
        ).count()
        # Choices reais: ativo, manutencao, parado.
        # O KPI "Parados" conta status=parado (único estado não ativo
        # além da manutenção, já exibida à parte). Não existe status "inativo".
        context["parados"] = equipamentos.filter(status="parado").count()
        context["inativos"] = context["parados"]

        # ============================================================
        # PRODUÇÃO
        # ============================================================

        producoes = Producao.objects.all()

        producao_hoje = (
            producoes.filter(
                data_hora__gte=inicio_hoje,
                data_hora__lt=fim_hoje,
            )
            .aggregate(total=Sum("quantidade"))["total"]
            or 0
        )

        producao_semana = (
            producoes.filter(
                data_hora__gte=inicio_semana_dt,
                data_hora__lt=fim_hoje,
            )
            .aggregate(total=Sum("quantidade"))["total"]
            or 0
        )

        producao_mes = (
            producoes.filter(
                data_hora__gte=inicio_mes_dt,
                data_hora__lt=fim_hoje,
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

        estoques = calcular_estoques_produto_por_peso(3, 5)
        estoque_5kg = estoques[5]
        estoque_3kg = estoques[3]

        total_estoque_gelo = estoque_5kg + estoque_3kg

        context["estoque_5kg_sacos"] = estoque_5kg
        context["estoque_3kg_sacos"] = estoque_3kg
        context["total_estoque_gelo_sacos"] = total_estoque_gelo

        # ============================================================
        # ESTOQUE DE EMBALAGENS
        # ============================================================

        embalagens = calcular_estoques_insumo_por_nome(
            "Embalagem Gelo 5k",
            "Embalagem Gelo 3k",
        )
        estoque_embalagem_5kg = embalagens["Embalagem Gelo 5k"]
        estoque_embalagem_3kg = embalagens["Embalagem Gelo 3k"]

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