from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from core.periodo import dia_local_atual
from financeiro.models import (
    CategoriaFinanceira,
    ContaPagar,
    ContaRecorrente,
    Fornecedor,
    ManutencaoVeiculo,
    ObrigacaoVeiculo,
)
from financeiro.services.dashboard import (
    JANELA_VENCIMENTO_DIAS,
    PERIODO_ESTE_MES,
    PERIODO_PERSONALIZADO,
    montar_dashboard,
    resolver_periodo,
)
from financeiro.tests_veiculos import criar_veiculo


HOJE = date(2026, 9, 12)


def _categoria(slug="aluguel"):
    return CategoriaFinanceira.objects.get(slug=slug)


def _conta(**kwargs):
    dados = {
        "descricao": "Conta dash",
        "categoria": _categoria(),
        "competencia": date(2026, 9, 1),
        "valor": Decimal("100.00"),
        "data_vencimento": HOJE,
        "status": ContaPagar.STATUS_PENDENTE,
    }
    dados.update(kwargs)
    return ContaPagar.objects.create(**dados)


class PeriodoDashboardTests(TestCase):
    def test_este_mes(self):
        chave, inicio, fim = resolver_periodo({}, hoje=HOJE)
        self.assertEqual(chave, PERIODO_ESTE_MES)
        self.assertEqual(inicio, date(2026, 9, 1))
        self.assertEqual(fim, date(2026, 9, 30))

    def test_personalizado_pela_url(self):
        chave, inicio, fim = resolver_periodo(
            {"inicio": "2026-08-01", "fim": "2026-08-31"},
            hoje=HOJE,
        )
        self.assertEqual(chave, PERIODO_PERSONALIZADO)
        self.assertEqual(inicio, date(2026, 8, 1))
        self.assertEqual(fim, date(2026, 8, 31))


class DashboardCalculosTests(TestCase):
    def setUp(self):
        self.energia = _categoria("energia-eletrica")
        self.aluguel = _categoria("aluguel")

    def _dash(self, **params):
        return montar_dashboard(params, hoje=HOJE)

    def test_sem_dados(self):
        dash = self._dash()
        self.assertFalse(dash.pendentes.visivel)
        self.assertFalse(dash.vencidas.visivel)
        self.assertFalse(dash.pagas.visivel)
        self.assertEqual(dash.pagas.total, Decimal("0.00"))
        self.assertEqual(dash.categorias, [])

    def test_pendente_nao_entra_no_pago(self):
        _conta(
            descricao="Aluguel pendente",
            valor=Decimal("2000.00"),
            data_vencimento=HOJE + timedelta(days=5),
        )
        dash = self._dash()
        self.assertTrue(dash.pendentes.visivel)
        self.assertEqual(dash.pendentes.total, Decimal("2000.00"))
        self.assertFalse(dash.pagas.visivel)
        self.assertEqual(dash.pagas.total, Decimal("0.00"))

    def test_vencida_nao_entra_no_pago(self):
        _conta(
            descricao="Conta atrasada",
            valor=Decimal("350.00"),
            data_vencimento=HOJE - timedelta(days=3),
        )
        dash = self._dash()
        self.assertTrue(dash.vencidas.visivel)
        self.assertEqual(dash.vencidas.total, Decimal("350.00"))
        self.assertEqual(dash.contas_vencidas[0].dias_atraso, 3)
        self.assertFalse(dash.pagas.visivel)

    def test_pago_no_periodo(self):
        _conta(
            descricao="Energia paga",
            categoria=self.energia,
            valor=Decimal("230.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 9, 5),
            forma_pagamento=ContaPagar.FORMA_PIX,
        )
        _conta(
            descricao="Aluguel pago",
            categoria=self.aluguel,
            valor=Decimal("1800.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 9, 8),
            forma_pagamento=ContaPagar.FORMA_BOLETO,
        )
        dash = self._dash()
        self.assertEqual(dash.pagas.quantidade, 2)
        self.assertEqual(dash.pagas.total, Decimal("2030.00"))
        self.assertEqual(dash.categorias[0].nome, "Aluguel")
        self.assertEqual(dash.categorias[0].total, Decimal("1800.00"))
        self.assertEqual(len(dash.chart_evolucao["labels"]), 30)
        self.assertEqual(len(dash.formas_pagamento), 2)

    def test_pago_fora_do_periodo_ignorado(self):
        _conta(
            descricao="Agosto",
            valor=Decimal("500.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 8, 20),
        )
        dash = self._dash()
        self.assertFalse(dash.pagas.visivel)

    def test_filtro_personalizado(self):
        _conta(
            descricao="Agosto",
            valor=Decimal("500.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 8, 20),
        )
        dash = self._dash(inicio="2026-08-01", fim="2026-08-31")
        self.assertEqual(dash.pagas.total, Decimal("500.00"))
        self.assertEqual(dash.periodo, PERIODO_PERSONALIZADO)

    def test_comparacao_com_mes_anterior(self):
        _conta(
            descricao="Ago",
            valor=Decimal("1000.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 8, 10),
        )
        _conta(
            descricao="Set",
            valor=Decimal("1200.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 9, 10),
        )
        dash = self._dash()
        self.assertEqual(dash.comparacao_atual, Decimal("1200.00"))
        self.assertEqual(dash.comparacao_anterior, Decimal("1000.00"))
        self.assertEqual(dash.comparacao_percentual, Decimal("20.00"))

    def test_vencendo_usa_janela_centralizada(self):
        _conta(
            descricao="Quase vencendo",
            valor=Decimal("80.00"),
            data_vencimento=HOJE + timedelta(days=JANELA_VENCIMENTO_DIAS),
        )
        _conta(
            descricao="Depois da janela",
            valor=Decimal("90.00"),
            data_vencimento=HOJE + timedelta(days=JANELA_VENCIMENTO_DIAS + 1),
        )
        dash = self._dash()
        self.assertEqual(dash.janela_dias, JANELA_VENCIMENTO_DIAS)
        self.assertEqual(dash.vencendo.quantidade, 1)
        self.assertEqual(dash.pendentes.quantidade, 2)


class DashboardVeiculosTests(TestCase):
    def test_gastos_veiculo_e_manutencao_sem_duplicar(self):
        veiculo = criar_veiculo()
        manutencao = ManutencaoVeiculo.objects.create(
            veiculo=veiculo,
            data_realizacao=date(2026, 9, 1),
            km_realizacao=51000,
            descricao="Revisão",
        )
        categoria = _categoria("manutencao")
        _conta(
            descricao="Peças",
            categoria=categoria,
            valor=Decimal("400.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 9, 4),
            veiculo=veiculo,
            manutencao=manutencao,
        )
        _conta(
            descricao="Combustível",
            categoria=_categoria("combustivel"),
            valor=Decimal("200.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 9, 4),
            veiculo=veiculo,
        )
        dash = montar_dashboard(
            {},
            permissoes={"financeiro.view_veiculo"},
            hoje=HOJE,
        )
        self.assertEqual(dash.gastos_veiculos.total, Decimal("600.00"))
        self.assertEqual(dash.gastos_veiculos.quantidade, 2)
        self.assertEqual(dash.manutencao.total, Decimal("400.00"))
        self.assertEqual(dash.manutencao.quantidade, 1)
        self.assertTrue(dash.veiculos)

    def test_obrigacao_isenta_nao_aparece_como_pendente(self):
        veiculo = criar_veiculo(ano_fabricacao=2004, ano_modelo=2005)
        ObrigacaoVeiculo.objects.create(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_IPVA,
            exercicio=2026,
            status=ObrigacaoVeiculo.STATUS_ISENTO,
        )
        ObrigacaoVeiculo.objects.create(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_LICENCIAMENTO,
            exercicio=2026,
            status=ObrigacaoVeiculo.STATUS_PENDENTE,
            data_vencimento=HOJE + timedelta(days=10),
        )
        dash = montar_dashboard(
            {},
            permissoes={"financeiro.view_veiculo"},
            hoje=HOJE,
        )
        tipos = [item["obrigacao"].tipo for item in dash.obrigacoes]
        self.assertEqual(tipos, [ObrigacaoVeiculo.TIPO_LICENCIAMENTO])

    def test_recorrencia_ainda_nao_gerada(self):
        ContaRecorrente.objects.create(
            descricao="Internet",
            categoria=_categoria("internet-telefonia"),
            valor=Decimal("120.00"),
            dia_vencimento=10,
            data_inicio=date(2026, 1, 1),
            ativa=True,
        )
        dash = montar_dashboard(
            {},
            permissoes={"financeiro.view_contarecorrente"},
            hoje=HOJE,
        )
        self.assertEqual(len(dash.recorrencias), 1)
        self.assertEqual(dash.recorrencias[0].descricao, "Internet")

    def test_recorrencia_ja_gerada_oculta(self):
        recorrente = ContaRecorrente.objects.create(
            descricao="Internet",
            categoria=_categoria("internet-telefonia"),
            valor=Decimal("120.00"),
            dia_vencimento=10,
            data_inicio=date(2026, 1, 1),
            ativa=True,
        )
        _conta(
            descricao="Internet",
            categoria=_categoria("internet-telefonia"),
            competencia=date(2026, 9, 1),
            recorrente=recorrente,
            data_vencimento=date(2026, 9, 10),
        )
        dash = montar_dashboard(
            {},
            permissoes={"financeiro.view_contarecorrente"},
            hoje=HOJE,
        )
        self.assertEqual(dash.recorrencias, [])


class DashboardUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="fin-dash-ok", password="teste-123"
        )
        conceder_permissoes(self.com_perm, "financeiro.view_contapagar")
        self.sem_perm = User.objects.create_user(
            username="fin-dash-sem", password="teste-123"
        )

    def test_anonimo_redireciona(self):
        response = self.client.get(reverse("financeiro:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("financeiro:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_autorizado_acessa_vazio(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visão geral das despesas")
        self.assertContains(response, "Sem despesas no período")
        self.assertNotContains(response, "Contas vencidas: R$ 0,00")
        self.assertContains(response, "Não há próximos vencimentos.")

    def test_mostra_pendente_e_oculta_pago_zero(self):
        hoje = dia_local_atual()
        _conta(
            descricao="Aluguel loja",
            valor=Decimal("1800.00"),
            competencia=hoje.replace(day=1),
            data_vencimento=hoje + timedelta(days=4),
        )
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:dashboard"))
        self.assertContains(response, "Aluguel loja")
        self.assertContains(response, "Pendentes")
        self.assertNotContains(response, "Pago no período")

    def test_filtro_periodo_na_url(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(
            reverse("financeiro:dashboard"),
            {"inicio": "2026-08-01", "fim": "2026-08-31"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dashboard"].inicio, date(2026, 8, 1))

    def test_lista_sem_fornecedor(self):
        _conta(descricao="Sem fornecedor", fornecedor=None)
        Fornecedor.objects.create(nome="Com fornecedor")
        self.client.force_login(self.com_perm)
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {"sem_fornecedor": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sem fornecedor")


class AgrupamentoEvolucaoTests(TestCase):
    def test_periodo_curto_diario(self):
        _conta(
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=HOJE,
            valor=Decimal("10.00"),
        )
        dash = montar_dashboard({}, permissoes=set(), hoje=HOJE)
        self.assertTrue(dash.chart_evolucao["labels"])
        self.assertRegex(dash.chart_evolucao["labels"][0], r"^\d{2}/\d{2}$")

    def test_periodo_longo_mensal(self):
        _conta(
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=date(2026, 8, 10),
            valor=Decimal("10.00"),
        )
        dash = montar_dashboard(
            {"inicio": "2026-07-01", "fim": "2026-09-12"},
            permissoes=set(),
            hoje=HOJE,
        )
        self.assertTrue(any("2026" in rotulo for rotulo in dash.chart_evolucao["labels"]))
