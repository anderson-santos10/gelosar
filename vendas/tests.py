from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
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
        conceder_permissoes(self.user, "vendas.add_venda")
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


class NovaVendaExcecoesNaoSilenciosasTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="excecao-vendedor",
            password="teste-123",
        )
        conceder_permissoes(self.user, "vendas.add_venda")
        self.cliente = Cliente.objects.create(nome="Cliente excecao venda")
        self.produto = Produto.objects.create(
            nome="Produto excecao venda",
            peso_kg=15,
            preco_venda="5.00",
        )
        self.http = Client()
        self.http.force_login(self.user)

    def _payload(self, quantidade="10"):
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

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_quantidade_nao_inteira_no_estoque_mostra_mensagem(self):
        with patch(
            "vendas.views.registrar_saidas_venda",
            side_effect=QuantidadeNaoInteira(
                "A quantidade deve ser um número inteiro de sacos."
            ),
        ):
            response = self.http.post(
                reverse("vendas:novo_pedido"),
                self._payload(quantidade="10"),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)
        self.assertContains(
            response,
            "A quantidade deve ser um número inteiro de sacos.",
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_itens_invalidos_mostra_mensagem(self):
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            self._payload(quantidade="10.50"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)
        self.assertContains(
            response,
            "Os itens do pedido são inválidos.",
        )
        self.assertContains(
            response,
            "Informe a quantidade em sacos inteiros.",
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_venda_valida_continua_criando_pedido_e_saida(self):
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            self._payload(quantidade="4"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.count(), 1)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            1,
        )


class ItemVendaFormsetPostTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="formset-vendedor",
            password="teste-123",
        )
        conceder_permissoes(self.user, "vendas.add_venda")
        self.cliente = Cliente.objects.create(nome="Cliente formset")
        self.produto = Produto.objects.create(
            nome="Produto formset A",
            peso_kg=11,
            preco_venda="6.00",
        )
        self.produto_b = Produto.objects.create(
            nome="Produto formset B",
            peso_kg=12,
            preco_venda="4.00",
        )
        self.http = Client()
        self.http.force_login(self.user)

    def _management(self, total_forms):
        return {
            "cliente": self.cliente.pk,
            "observacoes": "",
            "itens-TOTAL_FORMS": str(total_forms),
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
        }

    def test_pagina_inclui_campo_delete_do_formset(self):
        response = self.http.get(reverse("vendas:novo_pedido"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="itens-TOTAL_FORMS"')
        self.assertContains(response, 'name="itens-0-DELETE"')
        self.assertContains(response, 'name="itens-__prefix__-DELETE"')

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_um_item_cria_uma_venda_e_um_item(self):
        payload = self._management(1)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "10",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.count(), 1)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_dois_itens_validos_sao_persistidos(self):
        payload = self._management(2)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "3",
            "itens-1-produto": str(self.produto_b.pk),
            "itens-1-quantidade": "4",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.count(), 2)
        quantidades = set(
            ItemVenda.objects.values_list("quantidade", flat=True)
        )
        self.assertEqual(quantidades, {Decimal("3"), Decimal("4")})

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_item_marcado_delete_nao_e_persistido(self):
        payload = self._management(2)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "5",
            "itens-0-DELETE": "on",
            "itens-1-produto": str(self.produto_b.pk),
            "itens-1-quantidade": "8",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        itens = list(ItemVenda.objects.all())
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0].produto_id, self.produto_b.pk)
        self.assertEqual(itens[0].quantidade, Decimal("8"))

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_total_forms_com_indices_consecutivos_apos_adicionar_linha(self):
        payload = self._management(2)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "2",
            "itens-1-produto": str(self.produto_b.pk),
            "itens-1-quantidade": "6",
            "itens-1-DELETE": "on",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ItemVenda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.get().quantidade, Decimal("2"))


class VendaMinimoUmItemTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="min-item-vendedor",
            password="teste-123",
        )
        conceder_permissoes(self.user, "vendas.add_venda")
        self.cliente = Cliente.objects.create(nome="Cliente minimo item")
        self.produto = Produto.objects.create(
            nome="Produto minimo A",
            peso_kg=13,
            preco_venda="6.00",
        )
        self.produto_b = Produto.objects.create(
            nome="Produto minimo B",
            peso_kg=14,
            preco_venda="4.00",
        )
        self.http = Client()
        self.http.force_login(self.user)

    def _management(self, total_forms):
        return {
            "cliente": self.cliente.pk,
            "observacoes": "",
            "itens-TOTAL_FORMS": str(total_forms),
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
        }

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_venda_sem_itens_nao_e_criada(self):
        payload = self._management(0)
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_somente_formulario_vazio_nao_cria_venda(self):
        payload = self._management(1)
        payload.update({
            "itens-0-produto": "",
            "itens-0-quantidade": "",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertContains(
            response,
            "A venda deve possuir pelo menos um item.",
        )

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_um_item_valido_cria_venda(self):
        payload = self._management(1)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "10",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.count(), 1)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_dois_itens_validos_cria_venda(self):
        payload = self._management(2)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "2",
            "itens-1-produto": str(self.produto_b.pk),
            "itens-1-quantidade": "3",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.count(), 2)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_unico_item_com_delete_nao_cria_venda(self):
        payload = self._management(1)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "5",
            "itens-0-DELETE": "on",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)
        self.assertContains(
            response,
            "A venda deve possuir pelo menos um item.",
        )

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_item_valido_mais_linha_vazia_persiste_somente_o_valido(self):
        payload = self._management(2)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "4",
            "itens-1-produto": "",
            "itens-1-quantidade": "",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.get().quantidade, Decimal("4"))

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_item_valido_mais_delete_persiste_somente_o_valido(self):
        payload = self._management(2)
        payload.update({
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "7",
            "itens-0-DELETE": "on",
            "itens-1-produto": str(self.produto_b.pk),
            "itens-1-quantidade": "9",
        })
        response = self.http.post(reverse("vendas:novo_pedido"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.count(), 1)
        self.assertEqual(ItemVenda.objects.get().produto_id, self.produto_b.pk)


class VendaAdminSaidaTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="admin-vendas",
            password="teste-123",
        )
        self.cliente = Cliente.objects.create(nome="Cliente admin venda")
        self.produto = Produto.objects.create(
            nome="Produto admin venda",
            peso_kg=8,
            preco_venda="6.00",
        )
        self.http = Client()
        self.http.force_login(self.user)

    def _payload_add(self, quantidade=5):
        return {
            "cliente": self.cliente.pk,
            "observacoes": "",
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": str(quantidade),
            "_save": "Salvar",
        }

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_admin_cria_saida_com_produto_e_quantidade(self):
        response = self.http.post(
            reverse("admin:vendas_venda_add"),
            self._payload_add(quantidade=5),
        )
        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.get()
        item = ItemVenda.objects.get(venda=venda)
        saidas = MovimentacaoProduto.objects.filter(tipo="SAIDA")
        self.assertEqual(saidas.count(), 1)
        saida = saidas.get()
        self.assertEqual(saida.produto_id, self.produto.pk)
        self.assertEqual(saida.quantidade, 5)
        self.assertIn(f"venda #{venda.id}", saida.observacao)
        self.assertEqual(item.quantidade, Decimal("5"))

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_admin_respeita_corte_ausente_e_nao_gera_saida(self):
        response = self.http.post(
            reverse("admin:vendas_venda_add"),
            self._payload_add(quantidade=5),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            0,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2099, 1, 1))
    def test_admin_respeita_corte_futuro_e_nao_gera_saida(self):
        response = self.http.post(
            reverse("admin:vendas_venda_add"),
            self._payload_add(quantidade=5),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            0,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_admin_nao_duplica_saida_na_criacao(self):
        self.http.post(
            reverse("admin:vendas_venda_add"),
            self._payload_add(quantidade=5),
        )
        venda = Venda.objects.get()
        self.assertEqual(
            MovimentacaoProduto.objects.filter(
                tipo="SAIDA",
                produto=self.produto,
            ).count(),
            1,
        )
        item = ItemVenda.objects.get(venda=venda)
        response = self.http.post(
            reverse("admin:vendas_venda_change", args=[venda.pk]),
            {
                "cliente": self.cliente.pk,
                "observacoes": "edicao",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "1",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-id": str(item.pk),
                "itens-0-produto": str(self.produto.pk),
                "itens-0-quantidade": "5",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            1,
        )


class PoliticaDataCorteSemBackfillTests(TestCase):

    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente corte backfill")
        self.produto = Produto.objects.create(
            nome="Produto corte backfill",
            peso_kg=9,
            preco_venda="3.00",
        )

    def _criar_venda(self, data_venda):
        venda = Venda.objects.create(cliente=self.cliente)
        Venda.objects.filter(pk=venda.pk).update(data=data_venda)
        venda.refresh_from_db()
        ItemVenda.objects.create(
            venda=venda,
            produto=self.produto,
            quantidade=7,
        )
        return venda

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_definir_corte_depois_nao_cria_saida_historica(self):
        venda = self._criar_venda(date(2026, 9, 5))
        registrar_saidas_venda(venda)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            0,
        )
        with override_settings(ESTOQUE_DATA_CORTE=date(2026, 9, 1)):
            self.assertEqual(
                MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
                0,
            )
            venda.refresh_from_db()
            self.assertTrue(Venda.objects.filter(pk=venda.pk).exists())
            self.assertEqual(ItemVenda.objects.filter(venda=venda).count(), 1)

    def test_admin_e_tela_normal_usam_o_mesmo_servico(self):
        from vendas.admin import VendaAdmin
        from vendas.views import nova_venda
        import inspect

        self.assertIn(
            "registrar_saidas_venda",
            inspect.getsource(VendaAdmin.save_related),
        )
        self.assertIn(
            "registrar_saidas_venda",
            inspect.getsource(nova_venda),
        )


class VendaClienteProtectTests(TestCase):

    def test_cliente_com_venda_nao_pode_ser_excluido(self):
        from django.db.models.deletion import ProtectedError

        cliente = Cliente.objects.create(nome="Cliente protect")
        produto = Produto.objects.create(
            nome="Produto protect",
            peso_kg=8,
            preco_venda="1.00",
        )
        venda = Venda.objects.create(cliente=cliente)
        ItemVenda.objects.create(venda=venda, produto=produto, quantidade=1)
        with self.assertRaises(ProtectedError):
            cliente.delete()
        self.assertTrue(Venda.objects.filter(pk=venda.pk).exists())


class VendaSaldoInsuficientePermiteSaidaTests(TestCase):
    """MÉDIO-007: não há bloqueio por saldo; negativo permanece visível."""

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_saida_mesmo_sem_estoque(self):
        cliente = Cliente.objects.create(nome="Cliente saldo")
        produto = Produto.objects.create(
            nome="Produto saldo",
            peso_kg=9,
            preco_venda="1.00",
        )
        venda = Venda.objects.create(cliente=cliente)
        ItemVenda.objects.create(venda=venda, produto=produto, quantidade=4)
        registrar_saidas_venda(venda)
        self.assertEqual(calcular_estoque_produto(produto=produto), -4)


class VendaTotaisEConsultasTests(TestCase):

    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente totais")
        self.produto = Produto.objects.create(
            nome="Produto totais",
            peso_kg=5,
            preco_venda=Decimal("10.00"),
        )
        self.venda = Venda.objects.create(cliente=self.cliente)
        ItemVenda.objects.create(
            venda=self.venda,
            produto=self.produto,
            quantidade=Decimal("2.00"),
        )
        ItemVenda.objects.create(
            venda=self.venda,
            produto=self.produto,
            quantidade=Decimal("3.00"),
        )

    def test_total_e_quantidade_total(self):
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.quantidade_total, Decimal("5.00"))
        self.assertEqual(self.venda.total, Decimal("50.00"))

    def test_propriedades_nao_consultam_itens_duas_vezes(self):
        venda = Venda.objects.get(pk=self.venda.pk)
        with self.assertNumQueries(1):
            total = venda.total
            quantidade = venda.quantidade_total
        self.assertEqual(total, Decimal("50.00"))
        self.assertEqual(quantidade, Decimal("5.00"))

    def test_prefetch_nao_gera_n_plus_one(self):
        outra = Venda.objects.create(cliente=self.cliente)
        ItemVenda.objects.create(
            venda=outra,
            produto=self.produto,
            quantidade=Decimal("1.00"),
        )
        vendas = list(Venda.objects.prefetch_related("itens"))
        with self.assertNumQueries(0):
            totais = [venda.total for venda in vendas]
            quantidades = [venda.quantidade_total for venda in vendas]
        self.assertEqual(len(totais), 2)
        self.assertEqual(sum(quantidades), Decimal("6.00"))


class VendaCriadoPorTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="vendedor-audit",
            password="teste-123",
        )
        self.outro = User.objects.create_user(
            username="outro-venda",
            password="teste-123",
        )
        conceder_permissoes(self.user, "vendas.add_venda")
        self.cliente = Cliente.objects.create(nome="Cliente audit venda")
        self.produto = Produto.objects.create(
            nome="Produto audit venda",
            peso_kg=11,
            preco_venda="5.00",
        )
        self.http = Client()
        self.http.force_login(self.user)

    def _payload(self):
        return {
            "cliente": self.cliente.pk,
            "observacoes": "",
            "criado_por": str(self.outro.pk),
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-produto": str(self.produto.pk),
            "itens-0-quantidade": "3",
        }

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_view_registra_usuario_e_ignora_campo_post(self):
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            self._payload(),
        )
        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.get()
        self.assertEqual(venda.criado_por_id, self.user.pk)
        self.assertNotEqual(venda.criado_por_id, self.outro.pk)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            1,
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2000, 1, 1))
    def test_admin_cria_com_usuario_e_edicao_nao_troca(self):
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            username="admin-audit-venda",
            password="teste-123",
        )
        self.http.force_login(admin_user)
        response = self.http.post(
            reverse("admin:vendas_venda_add"),
            {
                "cliente": self.cliente.pk,
                "observacoes": "",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(self.produto.pk),
                "itens-0-quantidade": "2",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.get()
        self.assertEqual(venda.criado_por_id, admin_user.pk)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="SAIDA").count(),
            1,
        )
        response = self.http.post(
            reverse("admin:vendas_venda_change", args=[venda.pk]),
            {
                "cliente": self.cliente.pk,
                "observacoes": "editado",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "1",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-id": str(venda.itens.get().pk),
                "itens-0-produto": str(self.produto.pk),
                "itens-0-quantidade": "2",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 302)
        venda.refresh_from_db()
        self.assertEqual(venda.criado_por_id, admin_user.pk)
