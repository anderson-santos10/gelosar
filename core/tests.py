from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from core.charts import (
    compras_cliente_por_mes,
    estoque_atual_gelo,
    mix_produtos_cliente,
    producao_por_dia,
    vendas_por_dia,
)
from equipamentos.models import Equipamento
from estoque.models import MovimentacaoProduto
from producao.models import Producao
from produtos.models import Produto
from vendas.models import ItemVenda, Venda


class ChartsTests(TestCase):

    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente gráfico")
        self.produto_5 = Produto.objects.create(
            nome="Gelo 5kg gráfico",
            peso_kg=Decimal("5.00"),
            preco_venda=Decimal("6.00"),
        )
        self.produto_3 = Produto.objects.create(
            nome="Gelo 3kg gráfico",
            peso_kg=Decimal("3.00"),
            preco_venda=Decimal("5.00"),
        )
        self.equipamento = Equipamento.objects.create(
            nome="Máquina gráfico",
            tipo="maquina_gelo",
        )

    def _criar_venda(self, data_venda, produto, quantidade):
        venda = Venda.objects.create(cliente=self.cliente)
        Venda.objects.filter(pk=venda.pk).update(data=data_venda)
        venda.refresh_from_db()
        ItemVenda.objects.create(
            venda=venda,
            produto=produto,
            quantidade=quantidade,
        )
        return venda

    def test_vendas_por_dia_sem_vendas_retorna_zeros(self):
        dados = vendas_por_dia(dias=7)
        self.assertEqual(len(dados["labels"]), 7)
        self.assertEqual(dados["values"], [0, 0, 0, 0, 0, 0, 0])

    def test_vendas_por_dia_agrega_total_do_dia(self):
        hoje = timezone.localdate()
        self._criar_venda(hoje, self.produto_5, 10)
        self._criar_venda(hoje, self.produto_3, 4)
        dados = vendas_por_dia(dias=7)
        self.assertEqual(dados["values"][-1], 80.0)

    def test_producao_por_dia_sem_registros_retorna_zeros(self):
        dados = producao_por_dia(dias=7)
        self.assertEqual(dados["datasets"][0]["data"], [0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(dados["datasets"][1]["data"], [0, 0, 0, 0, 0, 0, 0])

    def test_producao_por_dia_separa_3kg_e_5kg(self):
        agora = timezone.now()
        Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto_5,
            quantidade=20,
        )
        Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto_3,
            quantidade=8,
        )
        Producao.objects.filter(produto=self.produto_5).update(data_hora=agora)
        Producao.objects.filter(produto=self.produto_3).update(data_hora=agora)
        dados = producao_por_dia(dias=7)
        self.assertEqual(dados["datasets"][0]["data"][-1], 8)
        self.assertEqual(dados["datasets"][1]["data"][-1], 20)

    def test_estoque_atual_usa_service(self):
        MovimentacaoProduto.objects.create(
            produto=self.produto_5,
            tipo="ENTRADA",
            quantidade=15,
        )
        dados = estoque_atual_gelo()
        self.assertEqual(dados["labels"], ["Gelo 5kg", "Gelo 3kg"])
        self.assertEqual(dados["values"][0], 15)
        self.assertEqual(dados["values"][1], 0)

    def test_compras_cliente_por_mes_vazio(self):
        dados = compras_cliente_por_mes(self.cliente, meses=6)
        self.assertEqual(len(dados["labels"]), 6)
        self.assertEqual(dados["values"], [0, 0, 0, 0, 0, 0])

    def test_mix_produtos_cliente(self):
        dados = mix_produtos_cliente({"Gelo 5kg": 10, "Gelo 3kg": 3})
        self.assertEqual(dados["labels"], ["Gelo 5kg", "Gelo 3kg"])
        self.assertEqual(dados["values"], [10.0, 3.0])


class DashboardViewChartsTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="dash",
            password="teste-123",
        )
        self.client.force_login(self.user)

    def test_dashboard_carrega_com_graficos_vazios(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("chart_vendas", response.context)
        self.assertEqual(len(response.context["chart_vendas"]["labels"]), 7)
        self.assertContains(response, "chart-vendas-data")
        self.assertContains(response, "dashboard_charts.js")
