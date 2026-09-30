import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.template import Context, Template
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.test_utils import conceder_permissoes
from clientes.models import Cliente
from estoque.models import MovimentacaoProduto
from financeiro.models import ContaReceber
from produtos.models import Produto
from vendas.models import ItemPedido, ItemVenda, Pedido, Venda
from vendas.services import PedidoNaoAberto, entregar_pedido


class PedidoFluxoTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.operador = User.objects.create_user(
            username="operador-pedido",
            password="teste-123",
            first_name="Ana",
            last_name="Rota",
        )
        self.entregador = User.objects.create_user(
            username="quem-entrega",
            password="teste-123",
            first_name="Bruno",
            last_name="Rua",
        )
        self.vendedor = User.objects.create_user(
            username="vendedor-direto",
            password="teste-123",
        )
        conceder_permissoes(
            self.operador,
            "vendas.add_pedido",
            "vendas.view_pedido",
            "vendas.entregar_pedido",
            "vendas.add_venda",
            "vendas.view_venda",
        )
        conceder_permissoes(
            self.entregador,
            "vendas.view_pedido",
            "vendas.entregar_pedido",
            "vendas.view_venda",
        )
        conceder_permissoes(self.vendedor, "vendas.add_venda", "vendas.view_venda")
        self.cliente = Cliente.objects.create(
            nome="João da Silva",
            endereco="Rua das Flores, 120",
            cidade="Marília",
            ativo=True,
        )
        self.gelo_3 = Produto.objects.create(
            nome="Gelo 3 kg pedido",
            peso_kg=Decimal("3.00"),
            preco_venda="4.50",
        )
        self.gelo_5 = Produto.objects.create(
            nome="Gelo 5 kg pedido",
            peso_kg=Decimal("5.00"),
            preco_venda="7.00",
        )
        self.http = Client()
        self.http.force_login(self.operador)

    def _payload(self, **extras):
        dados = {
            "cliente": self.cliente.pk,
            "endereco": self.cliente.endereco,
            "cidade": self.cliente.cidade,
            "observacoes": "Entregar depois das 17h.",
            "itens-TOTAL_FORMS": "2",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "1",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-produto": str(self.gelo_5.pk),
            "itens-0-quantidade": "50",
            "itens-1-produto": "",
            "itens-1-quantidade": "",
        }
        dados.update(extras)
        return dados

    def _criar(self, **extras):
        return self.http.post(reverse("vendas:novo_pedido"), self._payload(**extras))

    def test_permissao_entregar_existe(self):
        self.assertTrue(
            Permission.objects.filter(
                content_type__app_label="vendas",
                codename="entregar_pedido",
            ).exists()
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2020, 1, 1))
    def test_salvar_pedido_nao_cria_venda_nem_baixa_estoque(self):
        response = self._criar()
        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(response.url, reverse("vendas:detalhe_pedido", args=[pedido.pk]))
        self.assertEqual(pedido.status, Pedido.STATUS_ABERTO)
        self.assertEqual(pedido.cliente, self.cliente)
        self.assertEqual(pedido.endereco, "Rua das Flores, 120")
        self.assertEqual(pedido.cidade, "Marília")
        self.assertEqual(pedido.observacoes, "Entregar depois das 17h.")
        self.assertEqual(pedido.criado_por, self.operador)
        self.assertIsNone(pedido.venda_id)
        self.assertIsNone(pedido.entregue_em)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(ContaReceber.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 0)
        item = ItemPedido.objects.get()
        self.assertEqual(item.quantidade, 50)
        self.assertEqual(item.produto, self.gelo_5)
        self.assertEqual(item.preco_unitario, Decimal("7.00"))
        self.assertEqual(item.subtotal, Decimal("350.00"))
        self.assertEqual(pedido.total, Decimal("350.00"))

        detalhe = self.http.get(response.url)
        self.assertContains(detalhe, "Pedido #")
        self.assertContains(detalhe, "Aberto")
        self.assertContains(detalhe, "Produto:")
        self.assertContains(detalhe, "Gelo 5 kg pedido")
        self.assertContains(detalhe, "Quantidade:")
        self.assertContains(detalhe, "50 ×")
        self.assertContains(detalhe, "Preço unitário:")
        self.assertContains(detalhe, "7,00")
        self.assertContains(detalhe, "Subtotal:")
        self.assertContains(detalhe, "350,00")
        self.assertContains(detalhe, "Pedido entregue")
        abertos = self.http.get(reverse("vendas:pedidos_abertos"))
        self.assertContains(abertos, "Aberto")
        self.assertContains(abertos, "João da Silva")

    @override_settings(ESTOQUE_DATA_CORTE=date(2020, 1, 1))
    def test_endereco_do_pedido_nao_segue_alteracao_do_cliente(self):
        self._criar(endereco="Rua da Entrega, 20", cidade="Marília")
        self.cliente.endereco = "Avenida Nova, 9"
        self.cliente.cidade = "Garça"
        self.cliente.save()
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.endereco, "Rua da Entrega, 20")
        self.assertEqual(pedido.cidade, "Marília")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.endereco, "Avenida Nova, 9")

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_cliente_sem_endereco_nao_cria_pedido(self):
        self.cliente.endereco = ""
        self.cliente.cidade = ""
        self.cliente.save()
        response = self._criar(endereco="", cidade="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Informe o endereço do cliente antes de salvar o pedido.",
        )
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 0)
        self.assertEqual(ContaReceber.objects.count(), 0)

    def test_tela_comeca_com_uma_linha_e_endereco_do_cliente(self):
        response = self.http.get(reverse("vendas:novo_pedido"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('class="form-control gs-input js-cliente-pedido"', html)
        self.assertIn(self.cliente.endereco, html)
        self.assertIn("Mar\\u00edlia", html)
        self.assertEqual(html.count('name="itens-0-produto"'), 1)
        self.assertNotIn('name="itens-1-produto"', html)
        self.assertIn('name="itens-__prefix__-produto"', html)
        self.assertIn('name="itens-0-quantidade"', html)
        self.assertIn('value="1"', html)
        self.assertIn("\u00d7", html)
        self.assertNotIn(">Remover<", html)
        self.assertIn("Ex.: Rua das Flores, 123", html)
        self.assertIn("Ponto de referência, horário ou quem recebe", html)
        self.assertIn('id="itens-container"', html)
        self.assertIn('id="total-venda"', html)
        self.assertIn('class="form-control preco-input"', html)
        self.assertIn('class="subtotal"', html)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_post_sem_endereco_copia_o_cadastro_do_cliente(self):
        response = self._criar(endereco="", cidade="")
        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.endereco, "Rua das Flores, 120")
        self.assertEqual(pedido.cidade, "Marília")
        self.assertEqual(pedido.status, Pedido.STATUS_ABERTO)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 0)
        self.assertEqual(ContaReceber.objects.count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_sem_cliente_nao_cria_pedido(self):
        response = self._criar(cliente="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(Venda.objects.count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_quantidade_zero_nao_cria_pedido(self):
        response = self._criar(**{"itens-0-quantidade": "0"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A quantidade deve ser pelo menos 1 saco.")
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(Venda.objects.count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_quantidade_fracionada_e_rejeitada(self):
        response = self._criar(**{"itens-0-quantidade": "1.5"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe a quantidade em sacos inteiros.")
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(Venda.objects.count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_pedido_com_varios_produtos_guarda_preco(self):
        response = self._criar(**{
            "itens-1-produto": str(self.gelo_3.pk),
            "itens-1-quantidade": "20",
        })
        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        quantidades = {
            item.produto_id: item.quantidade
            for item in pedido.itens.all()
        }
        self.assertEqual(quantidades[self.gelo_5.id], 50)
        self.assertEqual(quantidades[self.gelo_3.id], 20)
        self.assertEqual(pedido.total, Decimal("440.00"))

    @override_settings(ESTOQUE_DATA_CORTE=date(2020, 1, 1))
    def test_entrega_cria_uma_venda_com_preco_do_pedido(self):
        self._criar()
        pedido = Pedido.objects.get()
        self.gelo_5.preco_venda = Decimal("99.00")
        self.gelo_5.save()
        self.http.force_login(self.entregador)
        response = self.http.post(reverse("vendas:entregar_pedido", args=[pedido.pk]))
        self.assertEqual(response.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.STATUS_ENTREGUE)
        self.assertEqual(pedido.entregue_por, self.entregador)
        self.assertTrue(timezone.is_aware(pedido.entregue_em))
        self.assertEqual(Venda.objects.count(), 1)
        venda = pedido.venda
        self.assertEqual(venda.cliente, self.cliente)
        self.assertEqual(venda.observacoes, pedido.observacoes)
        self.assertEqual(venda.criado_por, self.entregador)
        item_venda = ItemVenda.objects.get(venda=venda)
        self.assertEqual(item_venda.produto, self.gelo_5)
        self.assertEqual(item_venda.quantidade, Decimal("50"))
        item_venda.refresh_from_db()
        self.assertEqual(item_venda.preco_unitario, Decimal("7.00"))
        self.assertEqual(venda.total, Decimal("350.00"))
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 1)
        self.assertEqual(
            MovimentacaoProduto.objects.get(tipo="SAIDA").quantidade,
            50,
        )
        self.assertEqual(ContaReceber.objects.count(), 0)
        self.assertEqual(venda.pedido, pedido)

        abertos = self.http.get(reverse("vendas:pedidos_abertos"))
        self.assertContains(abertos, "Nenhum pedido em aberto")
        historico = self.http.get(reverse("vendas:historico_pedidos"))
        self.assertContains(historico, "João da Silva")
        self.assertContains(historico, f"#{venda.pk}")
        self.assertContains(historico, "Entregue")
        self.assertContains(historico, "gs-badge--ok")
        self.assertContains(historico, "Criado em")
        self.assertContains(historico, "R$ 350,00")

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_sem_data_corte_a_entrega_nao_baixa_estoque(self):
        self._criar()
        pedido = Pedido.objects.get()
        self.http.post(reverse("vendas:entregar_pedido", args=[pedido.pk]))
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=date(2020, 1, 1))
    def test_confirmar_duas_vezes_nao_duplica_venda_nem_estoque(self):
        self._criar()
        pedido = Pedido.objects.get()
        url = reverse("vendas:entregar_pedido", args=[pedido.pk])
        self.assertEqual(self.http.post(url).status_code, 302)
        pedido.refresh_from_db()
        entregue_em = pedido.entregue_em
        segunda = self.http.post(url)
        self.assertEqual(segunda.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.entregue_em, entregue_em)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 1)

    @override_settings(ESTOQUE_DATA_CORTE=date(2020, 1, 1))
    def test_falha_na_venda_nao_fecha_o_pedido(self):
        self._criar()
        pedido = Pedido.objects.get()
        with patch(
            "vendas.services.registrar_saidas_venda",
            side_effect=RuntimeError("falha de estoque"),
        ):
            with self.assertRaises(RuntimeError):
                entregar_pedido(pedido.pk, self.entregador)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.STATUS_ABERTO)
        self.assertIsNone(pedido.venda_id)
        self.assertIsNone(pedido.entregue_em)
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_pedido_entregue_nao_pode_ser_entregue_de_novo_pelo_servico(self):
        self._criar()
        pedido = Pedido.objects.get()
        entregar_pedido(pedido.pk, self.entregador)
        with self.assertRaises(PedidoNaoAberto):
            entregar_pedido(pedido.pk, self.operador)
        self.assertEqual(Venda.objects.count(), 1)

    def test_get_e_csrf_nao_entregam(self):
        self._criar()
        pedido = Pedido.objects.get()
        resposta = self.http.get(reverse("vendas:entregar_pedido", args=[pedido.pk]))
        self.assertEqual(resposta.status_code, 405)
        http = Client(enforce_csrf_checks=True)
        http.force_login(self.operador)
        negado = http.post(reverse("vendas:entregar_pedido", args=[pedido.pk]))
        self.assertEqual(negado.status_code, 403)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.STATUS_ABERTO)
        self.assertEqual(Venda.objects.count(), 0)

    def test_sem_permissao_de_entregar_nao_cria_venda(self):
        self._criar()
        pedido = Pedido.objects.get()
        self.http.force_login(self.vendedor)
        response = self.http.post(reverse("vendas:entregar_pedido", args=[pedido.pk]))
        self.assertEqual(response.status_code, 403)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.STATUS_ABERTO)
        self.assertEqual(Venda.objects.count(), 0)

    @override_settings(ESTOQUE_DATA_CORTE=None)
    def test_vendas_novo_cria_pedido_aberto_sem_venda(self):
        self.http.force_login(self.vendedor)
        response = self.http.post(
            reverse("vendas:novo_pedido"),
            {
                "cliente": self.cliente.pk,
                "observacoes": "Balcão",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(self.gelo_5.pk),
                "itens-0-quantidade": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Pedido.objects.count(), 1)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.status, Pedido.STATUS_ABERTO)
        self.assertEqual(pedido.endereco, self.cliente.endereco)
        self.assertEqual(ItemPedido.objects.get().preco_unitario, Decimal("7.00"))
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(ItemVenda.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.filter(tipo="SAIDA").count(), 0)

    def test_criador_ve_o_proprio_pedido_sem_view_pedido(self):
        self.http.force_login(self.vendedor)
        resposta = self.http.post(reverse("vendas:novo_pedido"), self._payload())
        pedido = Pedido.objects.get()
        self.assertEqual(resposta.status_code, 302)
        detalhe = self.http.get(resposta.url)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, "João da Silva")
        outro = Pedido.objects.create(
            cliente=self.cliente,
            endereco=self.cliente.endereco,
            cidade=self.cliente.cidade,
            status=Pedido.STATUS_ABERTO,
            criado_por=self.operador,
        )
        negado = self.http.get(reverse("vendas:detalhe_pedido", args=[outro.pk]))
        self.assertEqual(negado.status_code, 403)

    def test_lista_aberta_mostra_badge_e_valor_brasileiro(self):
        self._criar()
        resposta = self.http.get(reverse("vendas:pedidos_abertos"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Aberto")
        self.assertContains(resposta, "gs-badge--warning")
        self.assertContains(resposta, "Criado em")
        self.assertContains(resposta, "R$ 350,00")
        self.assertContains(resposta, "Pedido entregue")
        self.assertContains(resposta, "Pedidos em aberto")
        vazio = self.http.get(reverse("vendas:historico_pedidos"))
        self.assertContains(vazio, "Nenhum pedido entregue")

    def test_menu_separa_vendas_e_pedidos(self):
        resposta = self.http.get(reverse("vendas:pedidos_abertos"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Pedidos em aberto")
        self.assertContains(resposta, "Novo pedido")
        self.assertContains(resposta, "Histórico de pedidos")
        self.assertContains(resposta, "Vendas")
        self.http.force_login(self.vendedor)
        venda = self.http.get(reverse("vendas:novo_pedido"))
        self.assertEqual(venda.status_code, 200)
        self.assertNotContains(venda, "Pedidos em aberto")
        self.assertRedirects(
            self.http.get(reverse("vendas:cadastrar_pedido")),
            reverse("vendas:novo_pedido"),
        )

    def test_paginacao_de_pedidos_usa_gs_pagination(self):
        for _ in range(26):
            Pedido.objects.create(
                cliente=self.cliente,
                endereco=self.cliente.endereco,
                cidade=self.cliente.cidade,
                status=Pedido.STATUS_ABERTO,
                criado_por=self.operador,
            )
        primeira = self.http.get(reverse("vendas:pedidos_abertos"))
        self.assertContains(primeira, "gs-pagination")
        self.assertContains(primeira, "Página 1 de 2")
        self.assertContains(primeira, 'href="?page=2"')
        self.assertContains(primeira, 'aria-disabled="true"')
        self.assertNotContains(primeira, "pedido-paginacao")
        segunda = self.http.get(reverse("vendas:pedidos_abertos") + "?page=2")
        self.assertContains(segunda, "Página 2 de 2")
        self.assertContains(segunda, 'href="?page=1"')
        ultima = self.http.get(reverse("vendas:pedidos_abertos") + "?page=99")
        self.assertContains(ultima, "Página 2 de 2")
        sem_paginas = self.http.get(reverse("vendas:historico_pedidos"))
        self.assertNotContains(sem_paginas, "gs-pagination")


class MoedaBrFilterTests(SimpleTestCase):

    def test_moeda_br_formata_reais(self):
        template = Template("{% load moeda %}{{ valor|moeda_br }}")
        self.assertEqual(
            template.render(Context({"valor": 350})),
            "R$ 350,00",
        )
        self.assertEqual(
            template.render(Context({"valor": "1234.56"})),
            "R$ 1.234,56",
        )
        self.assertEqual(
            template.render(Context({"valor": Decimal("350.00")})),
            "R$ 350,00",
        )
