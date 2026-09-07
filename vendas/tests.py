from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from estoque.models import MovimentacaoProduto
from estoque.services import (
    QuantidadeNaoInteira,
    calcular_estoque_produto,
    registrar_saidas_venda,
    venda_deve_gerar_saida,
)
from produtos.models import Produto
from vendas.forms import ItemVendaForm
from vendas.models import ItemVenda, Venda


class IntegracaoVendaEstoqueTests(TestCase):

    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente teste estoque")
        self.produto_a = Produto.objects.create(
            nome="Produto A teste",
            peso_kg=1,
            preco_venda="10.00",
        )
        self.produto_b = Produto.objects.create(
            nome="Produto B teste",
            peso_kg=2,
            preco_venda="7.00",
        )

    def _criar_venda(self, data_venda, itens):
        venda = Venda.objects.create(cliente=self.cliente)
        Venda.objects.filter(pk=venda.pk).update(data=data_venda)
        venda.refresh_from_db()
        for produto, quantidade in itens:
            ItemVenda.objects.create(
                venda=venda,
                produto=produto,
                quantidade=quantidade,
            )
        return venda

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_sem_data_corte_nao_cria_saida(self):
        venda = self._criar_venda(
            date(2026, 9, 5),
            [(self.produto_a, 10)],
        )
        self.assertFalse(venda_deve_gerar_saida(venda))
        criadas = registrar_saidas_venda(venda)
        self.assertEqual(criadas, [])
        self.assertTrue(Venda.objects.filter(pk=venda.pk).exists())
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            0,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_venda_antes_da_data_corte_nao_cria_saida(self):
        venda = self._criar_venda(
            date(2026, 8, 31),
            [(self.produto_a, 10)],
        )
        criadas = registrar_saidas_venda(venda)
        self.assertEqual(criadas, [])
        self.assertEqual(
            MovimentacaoProduto.objects.filter(
                tipo="SAIDA",
                observacao__contains=f"venda #{venda.id}",
            ).count(),
            0,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_venda_exatamente_na_data_corte_cria_saida(self):
        venda = self._criar_venda(
            date(2026, 9, 1),
            [(self.produto_a, 8)],
        )
        criadas = registrar_saidas_venda(venda)
        self.assertEqual(len(criadas), 1)
        movimento = criadas[0]
        self.assertEqual(movimento.tipo, "SAIDA")
        self.assertEqual(movimento.produto, self.produto_a)
        self.assertEqual(movimento.quantidade, 8)

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_venda_depois_da_data_corte_cria_saida(self):
        venda = self._criar_venda(
            date(2026, 9, 5),
            [(self.produto_a, 4)],
        )
        criadas = registrar_saidas_venda(venda)
        self.assertEqual(len(criadas), 1)
        self.assertEqual(criadas[0].quantidade, 4)

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_venda_com_varios_itens_gera_uma_saida_por_item(self):
        venda = self._criar_venda(
            date(2026, 9, 5),
            [(self.produto_a, 10), (self.produto_b, 5)],
        )
        criadas = registrar_saidas_venda(venda)
        self.assertEqual(len(criadas), 2)
        por_produto = {m.produto_id: m.quantidade for m in criadas}
        self.assertEqual(por_produto[self.produto_a.id], 10)
        self.assertEqual(por_produto[self.produto_b.id], 5)

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_nao_duplica_saida_na_unica_chamada(self):
        venda = self._criar_venda(
            date(2026, 9, 5),
            [(self.produto_a, 3), (self.produto_b, 2)],
        )
        registrar_saidas_venda(venda)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(
                tipo="SAIDA",
                observacao=f"Saída automática referente à venda #{venda.id}",
            ).count(),
            2,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_saida_entra_no_calculo_oficial(self):
        MovimentacaoProduto.objects.create(
            produto=self.produto_a,
            tipo="ENTRADA",
            quantidade=100,
        )
        venda = self._criar_venda(
            date(2026, 9, 5),
            [(self.produto_a, 20)],
        )
        registrar_saidas_venda(venda)
        self.assertEqual(
            calcular_estoque_produto(produto=self.produto_a),
            80,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_quantidade_decimal_10_00_gera_saida_10(self):
        venda = self._criar_venda(
            date(2026, 9, 5),
            [(self.produto_a, Decimal("10.00"))],
        )
        criadas = registrar_saidas_venda(venda)
        self.assertEqual(len(criadas), 1)
        self.assertEqual(criadas[0].quantidade, 10)

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_quantidade_fracionada_nao_e_truncada(self):
        venda = self._criar_venda(
            date(2026, 9, 5),
            [(self.produto_a, Decimal("10.50"))],
        )
        with self.assertRaises(QuantidadeNaoInteira):
            registrar_saidas_venda(venda)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            0,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1))
    def test_dois_itens_inteiros_decimal_field(self):
        venda = self._criar_venda(
            date(2026, 9, 5),
            [
                (self.produto_a, Decimal("10.00")),
                (self.produto_b, Decimal("5.00")),
            ],
        )
        criadas = registrar_saidas_venda(venda)
        por_produto = {m.produto_id: m.quantidade for m in criadas}
        self.assertEqual(por_produto[self.produto_a.id], 10)
        self.assertEqual(por_produto[self.produto_b.id], 5)


class NovaVendaViewEstoqueTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="vendedor",
            password="teste-123",
        )
        self.cliente = Cliente.objects.create(nome="Cliente view")
        self.produto = Produto.objects.create(
            nome="Produto view",
            peso_kg=4,
            preco_venda="5.00",
        )
        self.http = Client()
        self.http.force_login(self.user)

    def _payload(self, quantidade=10):
        return {
            "cliente": self.cliente.pk,
            "observacoes": "",
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": str(quantidade),
        }

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_view_sem_corte_cria_venda_sem_saida(self):
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            self._payload(),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            0,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_view_com_corte_no_passado_cria_saida(self):
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            self._payload(quantidade=7),
        )
        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.get()
        self.assertGreaterEqual(venda.data, date(2000, 1, 1))
        movimentos = MovimentacaoProduto.objects.filter(
            tipo="SAIDA",
            produto=self.produto,
        )
        self.assertEqual(movimentos.count(), 1)
        self.assertEqual(movimentos.get().quantidade, 7)

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_view_falha_na_saida_desfaz_venda(self):
        with patch(
            "estoque.services.MovimentacaoProduto.objects.create",
            side_effect=RuntimeError("falha de teste"),
        ):
            with self.assertRaises(RuntimeError):
                self.http.post(
                    reverse("vendas:novo_pedido"),
                    self._payload(),
                )
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)

    def test_formulario_rejeita_quantidade_fracionada(self):
        form = ItemVendaForm(
            data={
                "produto": self.produto.pk,
                "quantidade": "10.50",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("quantidade", form.errors)

    def test_formulario_aceita_quantidade_inteira(self):
        form = ItemVendaForm(
            data={
                "produto": self.produto.pk,
                "quantidade": "10.00",
            }
        )
        self.assertTrue(form.is_valid())

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_view_quantidade_fracionada_nao_salva_venda(self):
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            self._payload(quantidade="10.50"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            0,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_view_item_invalido_desfaz_venda_inteira(self):
        produto_b = Produto.objects.create(
            nome="Produto view B",
            peso_kg=6,
            preco_venda="4.00",
        )
        payload = {
            "cliente": self.cliente.pk,
            "observacoes": "",
            "itens-TOTAL_FORMS": "2",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "10.00",
            "itens-1-produto": str(produto_b.pk),
            "itens-1-quantidade": "5.50",
        }
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            payload,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)

    def test_nova_venda_inclui_precos_no_contexto(self):
        response = self.http.get(reverse("vendas:novo_pedido"))
        self.assertEqual(response.status_code, 200)
        precos = response.context["produtos_precos_json"]
        self.assertEqual(precos[str(self.produto.pk)], "5.00")
        self.assertContains(response, "produtos-precos-data")
