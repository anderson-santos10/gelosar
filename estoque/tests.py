from datetime import date

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.conf import settings

from estoque.data_corte import parse_data_corte
from estoque.models import MovimentacaoProduto
from estoque.services import calcular_estoque_produto, calcular_saldo_oficial
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
