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
    Fornecedor,
    ManutencaoVeiculo,
    ObrigacaoVeiculo,
)
from financeiro.services.periodo import (
    PERIODO_MES_ANTERIOR,
    PERIODO_PERSONALIZADO,
    resolver_periodo,
)
from financeiro.services.relatorios import montar_relatorio
from financeiro.tests_veiculos import criar_veiculo

HOJE = date(2026, 9, 12)
PERMS_VEICULO = {"financeiro.view_veiculo", "financeiro.view_obrigacaoveiculo"}


def _cat(slug="aluguel"):
    return CategoriaFinanceira.objects.get(slug=slug)


def _pago(**kwargs):
    dados = {
        "descricao": "Pago",
        "categoria": _cat(),
        "competencia": date(2026, 9, 1),
        "valor": Decimal("100.00"),
        "data_vencimento": date(2026, 9, 5),
        "status": ContaPagar.STATUS_PAGO,
        "data_pagamento": date(2026, 9, 8),
    }
    dados.update(kwargs)
    return ContaPagar.objects.create(**dados)


class RelatorioDespesasTests(TestCase):
    def test_periodo_mes_anterior(self):
        chave, inicio, fim = resolver_periodo(
            {"periodo": PERIODO_MES_ANTERIOR}, hoje=HOJE
        )
        self.assertEqual(inicio, date(2026, 8, 1))
        self.assertEqual(fim, date(2026, 8, 31))

    def test_sem_dados(self):
        rel = montar_relatorio({}, hoje=HOJE)
        self.assertFalse(rel.tem_despesas)
        self.assertEqual(rel.quantidade, 0)
        self.assertIsNone(rel.media)

    def test_pendente_e_vencida_nao_entram(self):
        ContaPagar.objects.create(
            descricao="Pendente",
            categoria=_cat(),
            competencia=date(2026, 9, 1),
            valor=Decimal("900.00"),
            data_vencimento=HOJE + timedelta(days=2),
            status=ContaPagar.STATUS_PENDENTE,
        )
        ContaPagar.objects.create(
            descricao="Vencida",
            categoria=_cat(),
            competencia=date(2026, 8, 1),
            valor=Decimal("400.00"),
            data_vencimento=HOJE - timedelta(days=4),
            status=ContaPagar.STATUS_PENDENTE,
        )
        rel = montar_relatorio({}, hoje=HOJE)
        self.assertEqual(rel.total, Decimal("0.00"))
        self.assertEqual(rel.compromissos["pendentes_qtd"], 1)
        self.assertEqual(rel.compromissos["vencidas_qtd"], 1)

    def test_pago_entra_por_data_pagamento(self):
        _pago(valor=Decimal("250.00"), data_pagamento=date(2026, 9, 3))
        _pago(
            descricao="Agosto",
            valor=Decimal("80.00"),
            data_pagamento=date(2026, 8, 20),
        )
        rel = montar_relatorio({}, hoje=HOJE)
        self.assertEqual(rel.quantidade, 1)
        self.assertEqual(rel.total, Decimal("250.00"))
        self.assertIsInstance(rel.total, Decimal)
        self.assertEqual(rel.media, Decimal("250.00"))
        self.assertEqual(rel.maior, Decimal("250.00"))

    def test_categorias_percentual(self):
        energia = _cat("energia-eletrica")
        _pago(categoria=energia, valor=Decimal("2500.00"))
        _pago(
            categoria=_cat("combustivel"),
            valor=Decimal("2500.00"),
            veiculo=criar_veiculo(),
        )
        rel = montar_relatorio({}, permissoes=PERMS_VEICULO, hoje=HOJE)
        self.assertEqual(len(rel.categorias), 2)
        self.assertEqual(rel.categorias[0]["percentual"], Decimal("50.00"))
        self.assertEqual(rel.total, Decimal("5000.00"))

    def test_fornecedor_vazio(self):
        _pago(fornecedor=None, valor=Decimal("70.00"))
        rel = montar_relatorio({}, hoje=HOJE)
        self.assertEqual(rel.fornecedores[0]["nome"], "Sem fornecedor")
        self.assertEqual(rel.fornecedores[0]["total"], Decimal("70.00"))

    def test_filtros_combinados(self):
        veiculo = criar_veiculo()
        posto = Fornecedor.objects.create(nome="Posto X")
        outro = Fornecedor.objects.create(nome="Outro")
        combustivel = _cat("combustivel")
        _pago(
            descricao="Alvo",
            categoria=combustivel,
            fornecedor=posto,
            veiculo=veiculo,
            forma_pagamento=ContaPagar.FORMA_PIX,
            valor=Decimal("120.00"),
        )
        _pago(
            descricao="Fora",
            categoria=combustivel,
            fornecedor=outro,
            veiculo=veiculo,
            forma_pagamento=ContaPagar.FORMA_PIX,
            valor=Decimal("50.00"),
        )
        rel = montar_relatorio(
            {
                "categoria": str(combustivel.pk),
                "fornecedor": str(posto.pk),
                "veiculo": str(veiculo.pk),
                "forma": ContaPagar.FORMA_PIX,
            },
            permissoes=PERMS_VEICULO,
            hoje=HOJE,
        )
        self.assertEqual(rel.quantidade, 1)
        self.assertEqual(rel.total, Decimal("120.00"))

    def test_filtro_id_invalido(self):
        _pago(valor=Decimal("10.00"))
        rel = montar_relatorio({"categoria": "99999"}, hoje=HOJE)
        self.assertEqual(rel.quantidade, 0)

    def test_periodo_personalizado(self):
        _pago(valor=Decimal("15.00"), data_pagamento=date(2026, 8, 12))
        rel = montar_relatorio(
            {"inicio": "2026-08-01", "fim": "2026-08-31"},
            hoje=HOJE,
        )
        self.assertEqual(rel.periodo, PERIODO_PERSONALIZADO)
        self.assertEqual(rel.total, Decimal("15.00"))

    def test_comparacao_aumento_e_reducao(self):
        _pago(valor=Decimal("2000.00"), data_pagamento=date(2026, 8, 10))
        _pago(valor=Decimal("2500.00"), data_pagamento=date(2026, 9, 10))
        rel = montar_relatorio({}, hoje=HOJE)
        self.assertEqual(rel.comparacao_anterior, Decimal("2000.00"))
        self.assertEqual(rel.comparacao_diferenca, Decimal("500.00"))
        self.assertEqual(rel.comparacao_percentual, Decimal("25.00"))
        ContaPagar.objects.filter(data_pagamento=date(2026, 9, 10)).update(
            valor=Decimal("1000.00")
        )
        rel2 = montar_relatorio({}, hoje=HOJE)
        self.assertEqual(rel2.comparacao_percentual, Decimal("-50.00"))

    def test_veiculo_sem_vinculo_separado(self):
        veiculo = criar_veiculo()
        _pago(valor=Decimal("30.00"), veiculo=veiculo, categoria=_cat("combustivel"))
        _pago(valor=Decimal("10.00"), veiculo=None, categoria=_cat("aluguel"))
        rel = montar_relatorio({}, permissoes=PERMS_VEICULO, hoje=HOJE)
        nomes = [item["nome"] for item in rel.veiculos]
        self.assertIn("Sem veículo", nomes)
        self.assertEqual(len(rel.veiculos), 2)


class RelatorioManutencaoJoinTests(TestCase):
    def test_multiplas_contas_nao_duplicam_total(self):
        veiculo = criar_veiculo()
        manutencao = ManutencaoVeiculo.objects.create(
            veiculo=veiculo,
            data_realizacao=date(2026, 9, 2),
            km_realizacao=52000,
            descricao="Revisão",
        )
        categoria = _cat("manutencao")
        _pago(
            descricao="Peças",
            categoria=categoria,
            veiculo=veiculo,
            manutencao=manutencao,
            valor=Decimal("500.00"),
        )
        _pago(
            descricao="Mão de obra",
            categoria=categoria,
            veiculo=veiculo,
            manutencao=manutencao,
            valor=Decimal("300.00"),
        )
        rel = montar_relatorio({}, permissoes=PERMS_VEICULO, hoje=HOJE)
        self.assertEqual(len(rel.manutencoes), 1)
        linha = rel.manutencoes[0]
        self.assertEqual(linha["qtd_manutencoes"], 1)
        self.assertEqual(linha["qtd_contas"], 2)
        self.assertEqual(linha["total"], Decimal("800.00"))
        self.assertIsInstance(linha["total"], Decimal)
        self.assertNotEqual(linha["total"], Decimal("1600.00"))


class RelatorioObrigacoesTests(TestCase):
    def test_ipva_isento_nao_e_pendente(self):
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
        )
        ObrigacaoVeiculo.objects.create(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_SEGURO,
            exercicio=2026,
            status=ObrigacaoVeiculo.STATUS_PENDENTE,
        )
        rel = montar_relatorio(
            {"status_obrigacao": "pendente"},
            permissoes=PERMS_VEICULO,
            hoje=HOJE,
        )
        tipos = [item["obrigacao"].tipo for item in rel.obrigacoes]
        self.assertNotIn(ObrigacaoVeiculo.TIPO_IPVA, tipos)
        self.assertIn(ObrigacaoVeiculo.TIPO_LICENCIAMENTO, tipos)
        self.assertIn(ObrigacaoVeiculo.TIPO_SEGURO, tipos)

    def test_filtro_tipo_ipva_devido(self):
        veiculo = criar_veiculo()
        ObrigacaoVeiculo.objects.create(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_IPVA,
            exercicio=2026,
            status=ObrigacaoVeiculo.STATUS_PENDENTE,
        )
        rel = montar_relatorio(
            {"tipo": "ipva", "exercicio": "2026"},
            permissoes=PERMS_VEICULO,
            hoje=HOJE,
        )
        self.assertEqual(len(rel.obrigacoes), 1)
        self.assertEqual(rel.obrigacoes[0]["obrigacao"].status, "pendente")


class RelatorioUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="fin-rel-ok", password="teste-123"
        )
        conceder_permissoes(self.com_perm, "financeiro.view_contapagar")
        self.sem_perm = User.objects.create_user(
            username="fin-rel-sem", password="teste-123"
        )

    def test_anonimo_redireciona(self):
        response = self.client.get(reverse("financeiro:relatorios"))
        self.assertEqual(response.status_code, 302)

    def test_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        self.assertEqual(
            self.client.get(reverse("financeiro:relatorios")).status_code, 403
        )

    def test_autorizado_vazio(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:relatorios"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não há despesas no período selecionado.")
        self.assertContains(response, "Compromissos financeiros")
        self.assertNotContains(response, "Total pago")

    def test_mostra_despesa_paga(self):
        hoje = dia_local_atual()
        _pago(
            descricao="Energia setembro",
            categoria=_cat("energia-eletrica"),
            competencia=hoje.replace(day=1),
            data_pagamento=hoje,
            valor=Decimal("321.00"),
        )
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:relatorios"))
        self.assertContains(response, "Energia elétrica")
        self.assertContains(response, "321")
        self.assertContains(response, "Relatórios")


class AgrupamentoRelatorioTests(TestCase):
    def test_mesmo_limite_do_dashboard(self):
        from financeiro.services.periodo import LIMITE_DIAS_AGRUPAMENTO_DIARIO
        from financeiro.services.relatorios import LIMITE_DIAS_AGRUPAMENTO_DIARIO as limite_rel

        self.assertEqual(LIMITE_DIAS_AGRUPAMENTO_DIARIO, 45)
        self.assertEqual(limite_rel, 45)

    def test_periodo_longo_mensal(self):
        _pago(data_pagamento=date(2026, 8, 10), valor=Decimal("15.00"))
        rel = montar_relatorio(
            {"inicio": "2026-07-01", "fim": "2026-09-12"},
            permissoes=set(),
            hoje=HOJE,
        )
        self.assertTrue(any("2026" in rotulo for rotulo in rel.chart_evolucao["labels"]))
