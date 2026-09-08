from datetime import date
from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.conf import settings
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from estoque.data_corte import parse_data_corte
from estoque.models import MovimentacaoInsumo, MovimentacaoProduto
from estoque.services import (
    calcular_estoque_insumo,
    calcular_estoque_produto,
    calcular_estoques_insumos,
    calcular_estoques_produto_por_peso,
    calcular_saldo_oficial,
    venda_deve_gerar_saida,
)
from insumos.models import Insumo
from produtos.models import Produto


class ParseDataCorteTests(SimpleTestCase):

    def test_ausente_retorna_none(self):
        self.assertIsNone(parse_data_corte(None))

    def test_vazio_retorna_none(self):
        self.assertIsNone(parse_data_corte(""))
        self.assertIsNone(parse_data_corte("   "))

    def test_formato_iso_valido(self):
        self.assertEqual(parse_data_corte("2026-09-08"), date(2026, 9, 8))

    def test_formato_invalido_nao_silencia(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_data_corte("08/09/2026")
        with self.assertRaises(ImproperlyConfigured):
            parse_data_corte("nao-e-data")


class SettingsDataCorteTests(SimpleTestCase):

    def test_data_corte_nao_configurada_e_none(self):
        self.assertIsNone(settings.ESTOQUE_DATA_CORTE)


class SaldoOficialTests(SimpleTestCase):

    def test_entrada_menos_saida_mais_ajuste(self):
        self.assertEqual(calcular_saldo_oficial(100, 20, 5), 85)

    def test_saldo_negativo_nao_vira_zero(self):
        self.assertEqual(calcular_saldo_oficial(20, 30, 0), -10)


class CalcularEstoqueProdutoTests(TestCase):

    def setUp(self):
        self.produto = Produto.objects.create(
            nome="Produto teste saldo",
            peso_kg=1,
            preco_venda="1.00",
        )

    def test_formula_com_ajuste(self):
        MovimentacaoProduto.objects.create(
            produto=self.produto,
            tipo="ENTRADA",
            quantidade=100,
        )
        MovimentacaoProduto.objects.create(
            produto=self.produto,
            tipo="SAIDA",
            quantidade=20,
        )
        MovimentacaoProduto.objects.create(
            produto=self.produto,
            tipo="AJUSTE",
            quantidade=5,
        )
        self.assertEqual(calcular_estoque_produto(produto=self.produto), 85)
        self.assertEqual(calcular_estoque_produto(peso_kg=1), 85)

    def test_saldo_negativo_visivel(self):
        MovimentacaoProduto.objects.create(
            produto=self.produto,
            tipo="ENTRADA",
            quantidade=20,
        )
        MovimentacaoProduto.objects.create(
            produto=self.produto,
            tipo="SAIDA",
            quantidade=30,
        )
        self.assertEqual(calcular_estoque_produto(produto=self.produto), -10)


class CalcularEstoqueConsultaUnicaTests(TestCase):

    def setUp(self):
        self.p5 = Produto.objects.create(
            nome="Gelo 5 arq",
            peso_kg=5,
            preco_venda="1.00",
        )
        self.p3 = Produto.objects.create(
            nome="Gelo 3 arq",
            peso_kg=3,
            preco_venda="1.00",
        )
        MovimentacaoProduto.objects.create(
            produto=self.p5, tipo="ENTRADA", quantidade=10
        )
        MovimentacaoProduto.objects.create(
            produto=self.p5, tipo="SAIDA", quantidade=4
        )
        MovimentacaoProduto.objects.create(
            produto=self.p5, tipo="AJUSTE", quantidade=1
        )
        MovimentacaoProduto.objects.create(
            produto=self.p3, tipo="SAIDA", quantidade=2
        )

    def test_produto_uma_consulta_mantem_formula(self):
        with self.assertNumQueries(1):
            saldo = calcular_estoque_produto(produto=self.p5)
        self.assertEqual(saldo, 7)

    def test_dois_pesos_uma_consulta(self):
        with self.assertNumQueries(1):
            saldos = calcular_estoques_produto_por_peso(3, 5)
        self.assertEqual(saldos[5], 7)
        self.assertEqual(saldos[3], -2)
        self.assertEqual(saldos[5], calcular_estoque_produto(peso_kg=5))
        self.assertEqual(saldos[3], calcular_estoque_produto(peso_kg=3))

    def test_zero_quando_nao_ha_movimento(self):
        vazio = Produto.objects.create(
            nome="Sem movimento",
            peso_kg=1,
            preco_venda="1.00",
        )
        self.assertEqual(calcular_estoque_produto(produto=vazio), 0)

    def test_insumos_em_lote_igual_ao_individual(self):
        a = Insumo.objects.create(nome="Insumo lote A")
        b = Insumo.objects.create(nome="Insumo lote B")
        MovimentacaoInsumo.objects.create(
            insumo=a, tipo="ENTRADA", quantidade=5
        )
        MovimentacaoInsumo.objects.create(
            insumo=a, tipo="SAIDA", quantidade=2
        )
        MovimentacaoInsumo.objects.create(
            insumo=b, tipo="AJUSTE", quantidade=3
        )
        with self.assertNumQueries(1):
            lote = calcular_estoques_insumos([a, b])
        self.assertEqual(lote[a], calcular_estoque_insumo(insumo=a))
        self.assertEqual(lote[b], calcular_estoque_insumo(insumo=b))
        self.assertEqual(lote[a], 3)
        self.assertEqual(lote[b], 3)


class PoliticaDataCorteVendaTests(SimpleTestCase):
    """
    ALTO-002 — política explícita de SAIDA automática.

    Comparação vigente: venda.data >= ESTOQUE_DATA_CORTE.
    None não é erro: desliga a SAIDA de venda.
    """

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_corte_ausente_nao_gera_saida(self):
        venda = SimpleNamespace(data=date(2026, 9, 10))
        self.assertFalse(venda_deve_gerar_saida(venda))

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 10))
    def test_venda_anterior_ao_corte_nao_gera_saida(self):
        venda = SimpleNamespace(data=date(2026, 9, 9))
        self.assertFalse(venda_deve_gerar_saida(venda))

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 10))
    def test_venda_na_data_do_corte_gera_saida(self):
        venda = SimpleNamespace(data=date(2026, 9, 10))
        self.assertTrue(venda_deve_gerar_saida(venda))

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 10))
    def test_venda_posterior_ao_corte_gera_saida(self):
        venda = SimpleNamespace(data=date(2026, 9, 11))
        self.assertTrue(venda_deve_gerar_saida(venda))


class SaldoInsumoTelaEstoqueTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="est-ok",
            password="teste-123",
        )
        conceder_permissoes(self.com_perm, "estoque.view_movimentacaoproduto")
        self.sem_perm = User.objects.create_user(
            username="est-sem",
            password="teste-123",
        )
        self.insumo_a = Insumo.objects.create(nome="Insumo A tela")
        self.insumo_b = Insumo.objects.create(nome="Insumo B tela")
        MovimentacaoInsumo.objects.create(
            insumo=self.insumo_a,
            tipo="ENTRADA",
            quantidade=10,
        )
        MovimentacaoInsumo.objects.create(
            insumo=self.insumo_a,
            tipo="SAIDA",
            quantidade=3,
        )
        MovimentacaoInsumo.objects.create(
            insumo=self.insumo_a,
            tipo="AJUSTE",
            quantidade=1,
        )
        MovimentacaoInsumo.objects.create(
            insumo=self.insumo_b,
            tipo="SAIDA",
            quantidade=2,
        )

    def test_saldos_na_pagina(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("estoque:estoque"))
        self.assertEqual(response.status_code, 200)
        saldos = {item["insumo"].pk: item["saldo"] for item in response.context["saldos_insumos"]}
        self.assertEqual(saldos[self.insumo_a.pk], 8)
        self.assertEqual(saldos[self.insumo_b.pk], -2)
        self.assertEqual(calcular_estoque_insumo(insumo=self.insumo_a), 8)

    def test_insumo_sem_movimento_saldo_zero(self):
        vazio = Insumo.objects.create(nome="Insumo vazio tela")
        self.assertEqual(calcular_estoque_insumo(insumo=vazio), 0)

    def test_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("estoque:estoque"))
        self.assertEqual(response.status_code, 403)


class AjusteProdutoUITests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="aj-ok",
            password="teste-123",
        )
        conceder_permissoes(self.com_perm, "estoque.add_movimentacaoproduto")
        self.sem_perm = User.objects.create_user(
            username="aj-sem",
            password="teste-123",
        )
        self.produto = Produto.objects.create(
            nome="Produto ajuste UI",
            peso_kg=7,
            preco_venda="1.00",
        )

    def test_ajuste_positivo_aumenta_saldo(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("estoque:ajuste_produto"),
            {"produto": self.produto.pk, "quantidade": "5", "observacao": "inventario"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(calcular_estoque_produto(produto=self.produto), 5)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="AJUSTE").count(),
            1,
        )

    def test_quantidade_zero_rejeitada(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("estoque:ajuste_produto"),
            {"produto": self.produto.pk, "quantidade": "0", "observacao": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)

    def test_quantidade_negativa_rejeitada(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("estoque:ajuste_produto"),
            {"produto": self.produto.pk, "quantidade": "-3", "observacao": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)

    def test_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("estoque:ajuste_produto"))
        self.assertEqual(response.status_code, 403)


class AlertaEstoqueZeradoOuNegativoTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="alerta-est",
            password="teste-123",
        )
        conceder_permissoes(self.user, "estoque.view_movimentacaoproduto")
        self.client.force_login(self.user)
        self.p5 = Produto.objects.create(
            nome="Gelo 5 alerta",
            peso_kg=5,
            preco_venda="1.00",
        )
        self.p3 = Produto.objects.create(
            nome="Gelo 3 alerta",
            peso_kg=3,
            preco_venda="1.00",
        )

    def test_estoque_zero_exibe_alerta(self):
        response = self.client.get(reverse("estoque:estoque"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["estoque_5kg_sacos"], 0)
        self.assertContains(response, "sem estoque disponível")

    def test_estoque_positivo_nao_exibe_alerta(self):
        MovimentacaoProduto.objects.create(
            produto=self.p5, tipo="ENTRADA", quantidade=2
        )
        MovimentacaoProduto.objects.create(
            produto=self.p3, tipo="ENTRADA", quantidade=2
        )
        response = self.client.get(reverse("estoque:estoque"))
        self.assertGreater(response.context["estoque_5kg_sacos"], 0)
        self.assertGreater(response.context["estoque_3kg_sacos"], 0)
        self.assertNotContains(response, "sem estoque disponível")

    def test_estoque_negativo_exibe_alerta(self):
        MovimentacaoProduto.objects.create(
            produto=self.p5, tipo="SAIDA", quantidade=3
        )
        MovimentacaoProduto.objects.create(
            produto=self.p3, tipo="ENTRADA", quantidade=1
        )
        response = self.client.get(reverse("estoque:estoque"))
        self.assertLess(response.context["estoque_5kg_sacos"], 0)
        self.assertContains(response, "sem estoque disponível")
