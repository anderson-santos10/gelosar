from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from equipamentos.models import Equipamento
from estoque.models import MovimentacaoInsumo, MovimentacaoProduto
from estoque.services import QuantidadeNaoInteira, quantidade_para_movimento
from insumos.models import Insumo
from producao.models import Producao
from produtos.models import ComposicaoProduto, Produto


class ConsumoInsumoProducaoTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="produtor",
            password="teste-123",
        )
        conceder_permissoes(self.user, "producao.add_producao")
        self.http = Client()
        self.http.force_login(self.user)
        self.equipamento = Equipamento.objects.create(
            nome="Máquina teste produção",
            tipo="maquina_gelo",
        )
        self.insumo = Insumo.objects.create(nome="Embalagem teste produção")

    def _criar_produto_com_composicao(self, nome, peso_kg, quantidade_composicao):
        produto = Produto.objects.create(
            nome=nome,
            peso_kg=peso_kg,
            preco_venda="1.00",
        )
        ComposicaoProduto.objects.create(
            produto=produto,
            insumo=self.insumo,
            quantidade=quantidade_composicao,
        )
        return produto

    def _payload(self, produto, quantidade):
        return {
            "equipamento": self.equipamento.pk,
            "produto": produto.pk,
            "quantidade": str(quantidade),
            "observacao": "",
        }

    def test_consumo_inteiro_gera_saida(self):
        produto = self._criar_produto_com_composicao(
            "Produto consumo 2",
            Decimal("2.00"),
            Decimal("2"),
        )
        response = self.http.post(
            reverse("producao:new_producao"),
            self._payload(produto, 3),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Producao.objects.count(), 1)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="ENTRADA").count(),
            1,
        )
        saida = MovimentacaoInsumo.objects.get(tipo="SAIDA")
        self.assertEqual(saida.quantidade, 6)
        self.assertEqual(saida.insumo, self.insumo)

    def test_consumo_decimal_nao_e_truncado(self):
        produto = self._criar_produto_com_composicao(
            "Produto consumo 1.5",
            Decimal("2.10"),
            Decimal("1.5"),
        )
        response = self.http.post(
            reverse("producao:new_producao"),
            self._payload(produto, 1),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Producao.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)
        self.assertEqual(MovimentacaoInsumo.objects.count(), 0)
        with self.assertRaises(QuantidadeNaoInteira):
            quantidade_para_movimento(Decimal("1.5") * 1)

    def test_consumo_menor_que_um_nao_gera_saida_zero(self):
        produto = self._criar_produto_com_composicao(
            "Produto consumo 0.5",
            Decimal("2.20"),
            Decimal("0.5"),
        )
        response = self.http.post(
            reverse("producao:new_producao"),
            self._payload(produto, 1),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Producao.objects.count(), 0)
        self.assertEqual(
            MovimentacaoInsumo.objects.filter(tipo="SAIDA").count(),
            0,
        )
        self.assertFalse(
            MovimentacaoInsumo.objects.filter(quantidade=0).exists()
        )

    def test_consumo_invalido_desfaz_entrada_do_produto(self):
        produto = self._criar_produto_com_composicao(
            "Produto atomicidade",
            Decimal("2.30"),
            Decimal("0.5"),
        )
        response = self.http.post(
            reverse("producao:new_producao"),
            self._payload(produto, 1),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Producao.objects.count(), 0)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="ENTRADA").count(),
            0,
        )
        self.assertEqual(MovimentacaoInsumo.objects.count(), 0)
        self.assertContains(
            response,
            "consumo de insumo não resulta em quantidade inteira",
        )


class ProducaoSemComposicaoTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="prod-sem-comp",
            password="teste-123",
        )
        conceder_permissoes(self.user, "producao.add_producao")
        self.http = Client()
        self.http.force_login(self.user)
        self.equipamento = Equipamento.objects.create(
            nome="Máquina sem composição",
            tipo="maquina_gelo",
        )

    def test_sem_composicao_nao_gera_entrada(self):
        produto = Produto.objects.create(
            nome="Produto sem BOM",
            peso_kg=Decimal("4.00"),
            preco_venda="1.00",
        )
        response = self.http.post(
            reverse("producao:new_producao"),
            {
                "equipamento": self.equipamento.pk,
                "produto": produto.pk,
                "quantidade": "2",
                "observacao": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Producao.objects.count(), 0)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)
        self.assertContains(response, "não possui composição")


class ProducaoDataCorteTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="prod-corte",
            password="teste-123",
        )
        conceder_permissoes(self.user, "producao.add_producao")
        self.http = Client()
        self.http.force_login(self.user)
        self.equipamento = Equipamento.objects.create(
            nome="Máquina corte",
            tipo="maquina_gelo",
        )
        self.insumo = Insumo.objects.create(nome="Emb corte")
        self.produto = Produto.objects.create(
            nome="Produto corte",
            peso_kg=Decimal("6.00"),
            preco_venda="1.00",
        )
        ComposicaoProduto.objects.create(
            produto=self.produto,
            insumo=self.insumo,
            quantidade=Decimal("1"),
        )

    @override_settings(ESTOQUE_DATA_CORTE=date(2099, 1, 1))
    def test_producao_gera_entrada_mesmo_com_corte_futuro(self):
        response = self.http.post(
            reverse("producao:new_producao"),
            {
                "equipamento": self.equipamento.pk,
                "produto": self.produto.pk,
                "quantidade": "2",
                "observacao": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="ENTRADA").count(),
            1,
        )


class ProducaoListSelectRelatedTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="prod-list",
            password="teste-123",
        )
        conceder_permissoes(self.user, "producao.view_producao")
        self.client.force_login(self.user)
        self.equipamento = Equipamento.objects.create(
            nome="Máquina lista",
            tipo="maquina_gelo",
        )
        self.produto = Produto.objects.create(
            nome="Gelo lista",
            peso_kg=Decimal("5.00"),
            preco_venda="1.00",
        )
        for i in range(4):
            Producao.objects.create(
                equipamento=self.equipamento,
                produto=self.produto,
                quantidade=i + 1,
            )

    def test_fks_precarregadas_nao_consultam_de_novo(self):
        from producao.views import ProducaoListView

        producoes = list(ProducaoListView().get_queryset())
        with self.assertNumQueries(0):
            nomes = [
                (producao.equipamento.nome, producao.produto.nome)
                for producao in producoes
            ]
        self.assertEqual(len(nomes), 4)

    def test_lista_renderiza_relacionamentos(self):
        response = self.client.get(reverse("producao:producao_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Máquina lista")
        self.assertContains(response, "Gelo lista")


class ProducaoCriadoPorTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="produtor-audit",
            password="teste-123",
        )
        self.outro = User.objects.create_user(
            username="outro-prod",
            password="teste-123",
        )
        conceder_permissoes(self.user, "producao.add_producao")
        self.http = Client()
        self.http.force_login(self.user)
        self.equipamento = Equipamento.objects.create(
            nome="Máquina audit",
            tipo="maquina_gelo",
        )
        self.insumo = Insumo.objects.create(nome="Emb audit")
        self.produto = Produto.objects.create(
            nome="Produto audit",
            peso_kg=Decimal("7.00"),
            preco_venda="1.00",
        )
        ComposicaoProduto.objects.create(
            produto=self.produto,
            insumo=self.insumo,
            quantidade=Decimal("1"),
        )

    def test_view_registra_usuario_autenticado(self):
        response = self.http.post(
            reverse("producao:new_producao"),
            {
                "equipamento": self.equipamento.pk,
                "produto": self.produto.pk,
                "quantidade": "4",
                "observacao": "",
                "criado_por": str(self.outro.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        producao = Producao.objects.get()
        self.assertEqual(producao.criado_por_id, self.user.pk)
        self.assertNotEqual(producao.criado_por_id, self.outro.pk)
        self.assertEqual(
            MovimentacaoProduto.objects.filter(tipo="ENTRADA").count(),
            1,
        )
        self.assertEqual(
            MovimentacaoInsumo.objects.filter(tipo="SAIDA").count(),
            1,
        )

    def test_admin_edicao_nao_troca_criador(self):
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            username="admin-prod",
            password="teste-123",
        )
        producao = Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto,
            quantidade=1,
            criado_por=self.user,
        )
        self.http.force_login(admin_user)
        response = self.http.post(
            reverse("admin:producao_producao_change", args=[producao.pk]),
            {
                "equipamento": self.equipamento.pk,
                "produto": self.produto.pk,
                "quantidade": "9",
                "observacao": "editado",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 403)
        producao.refresh_from_db()
        self.assertEqual(producao.criado_por_id, self.user.pk)
        self.assertEqual(producao.quantidade, 1)
        self.assertEqual(producao.observacao, "")


class ProducaoAdminConsultaTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="consulta-prod",
            password="teste-123",
            is_staff=True,
        )
        conceder_permissoes(
            self.staff,
            "producao.view_producao",
            "producao.add_producao",
            "producao.change_producao",
            "producao.delete_producao",
        )
        self.operador = User.objects.create_user(
            username="operador-prod",
            password="teste-123",
        )
        conceder_permissoes(self.operador, "producao.add_producao")
        self.http = Client()
        self.equipamento = Equipamento.objects.create(
            nome="Máquina consulta",
            tipo="maquina_gelo",
        )
        self.insumo = Insumo.objects.create(nome="Emb consulta")
        self.produto = Produto.objects.create(
            nome="Produto consulta",
            peso_kg=Decimal("8.00"),
            preco_venda="1.00",
        )
        ComposicaoProduto.objects.create(
            produto=self.produto,
            insumo=self.insumo,
            quantidade=Decimal("2"),
        )
        self.producao = Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto,
            quantidade=3,
            criado_por=self.operador,
        )

    def test_admin_nao_permite_adicionar(self):
        self.http.force_login(self.staff)
        self.assertEqual(
            self.http.get(reverse("admin:producao_producao_add")).status_code,
            403,
        )
        resposta = self.http.post(
            reverse("admin:producao_producao_add"),
            {
                "equipamento": self.equipamento.pk,
                "produto": self.produto.pk,
                "quantidade": "2",
                "observacao": "",
                "_save": "Salvar",
            },
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Producao.objects.count(), 1)
        self.assertEqual(MovimentacaoProduto.objects.count(), 0)
        self.assertEqual(MovimentacaoInsumo.objects.count(), 0)

    def test_admin_nao_permite_alterar(self):
        self.http.force_login(self.staff)
        resposta = self.http.post(
            reverse("admin:producao_producao_change", args=[self.producao.pk]),
            {
                "equipamento": self.equipamento.pk,
                "produto": self.produto.pk,
                "quantidade": "9",
                "observacao": "alterado pelo admin",
                "_save": "Salvar",
            },
        )
        self.assertEqual(resposta.status_code, 403)
        self.producao.refresh_from_db()
        self.assertEqual(self.producao.quantidade, 3)
        self.assertEqual(self.producao.observacao, "")

    def test_admin_nao_permite_excluir(self):
        self.http.force_login(self.staff)
        url = reverse("admin:producao_producao_delete", args=[self.producao.pk])
        self.assertEqual(self.http.get(url).status_code, 403)
        resposta = self.http.post(url, {"post": "yes"})
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(Producao.objects.filter(pk=self.producao.pk).exists())

    def test_usuario_com_view_consulta_lista_e_registro(self):
        self.http.force_login(self.staff)
        lista = self.http.get(reverse("admin:producao_producao_changelist"))
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, self.produto.nome)
        detalhe = self.http.get(
            reverse("admin:producao_producao_change", args=[self.producao.pk])
        )
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, self.produto.nome)

    def test_tela_operacional_continua_criando_producao_e_estoque(self):
        self.http.force_login(self.operador)
        resposta = self.http.post(
            reverse("producao:new_producao"),
            {
                "equipamento": self.equipamento.pk,
                "produto": self.produto.pk,
                "quantidade": "4",
                "observacao": "",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Producao.objects.count(), 2)
        entrada = MovimentacaoProduto.objects.get(tipo="ENTRADA")
        self.assertEqual(entrada.produto_id, self.produto.pk)
        self.assertEqual(entrada.quantidade, 4)
        saida = MovimentacaoInsumo.objects.get(tipo="SAIDA")
        self.assertEqual(saida.insumo_id, self.insumo.pk)
        self.assertEqual(saida.quantidade, 8)
