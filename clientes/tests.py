from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from decimal import Decimal
from pathlib import Path

from django.conf import settings

from accounts.test_utils import conceder_permissoes
from clientes.admin import ClienteAdmin
from clientes.models import Cliente
from equipamentos.models import Equipamento


class DashboardClienteViewTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cliente-dash",
            password="teste-123",
        )
        conceder_permissoes(self.user, "clientes.view_cliente")
        self.cliente = Cliente.objects.create(nome="Cliente dashboard")
        self.client.force_login(self.user)

    def test_dashboard_cliente_carrega_sem_historico(self):
        response = self.client.get(
            reverse("clientes:dashboard_cliente", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("chart_compras_mes", response.context)
        self.assertIn("chart_produtos", response.context)
        self.assertContains(response, "cliente_dashboard.js")
        self.assertContains(response, 'data-gs-sensitive')
        self.assertNotContains(response, "onclick=")

    def test_roi_e_metrica_gerencial_nao_contratual(self):
        Equipamento.objects.create(
            nome="Freezer cliente",
            tipo="freezer",
            cliente=self.cliente,
            valor_compra=Decimal("1000.00"),
        )
        response = self.client.get(
            reverse("clientes:dashboard_cliente", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["valor_investimento"], Decimal("1000.00"))
        self.assertEqual(response.context["valor_recuperado"], 0)
        self.assertContains(response, "ROI estimado")
        self.assertContains(response, "Métrica gerencial")
        self.assertContains(response, "Não é regra contratual de comodato")
        self.assertNotContains(response, "Retorno do investimento")

    def test_historico_usa_mesmo_mecanismo_sensivel(self):
        from produtos.models import Produto
        from vendas.models import ItemVenda, Venda

        produto = Produto.objects.create(
            nome="Gelo hist",
            peso_kg=Decimal("5.00"),
            preco_venda=Decimal("10.00"),
        )
        venda = Venda.objects.create(cliente=self.cliente)
        ItemVenda.objects.create(venda=venda, produto=produto, quantidade=2)
        response = self.client.get(
            reverse("clientes:dashboard_cliente", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'id="historico-venda-{venda.pk}"')
        self.assertContains(
            response,
            f'data-gs-sensitive-container="historico-venda-{venda.pk}"',
        )
        self.assertContains(response, "R$ ••••••")
        self.assertContains(response, "sensitive-value")
        self.assertContains(response, "sensitive-masked")


class ClienteAdminDashboardLinkTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_user(
            username="admin-clientes",
            password="teste-123",
            is_staff=True,
            is_superuser=True,
        )
        self.cliente = Cliente.objects.create(nome="Cliente admin")
        self.client.force_login(self.admin_user)

    def test_dashboard_link_usa_url_existente(self):
        admin = ClienteAdmin(Cliente, site)
        try:
            html = admin.dashboard_link(self.cliente)
        except NoReverseMatch:
            self.fail("ClienteAdmin.dashboard_link lançou NoReverseMatch")

        esperado = reverse("clientes:dashboard_cliente", args=[self.cliente.pk])
        self.assertEqual(esperado, f"/cliente/{self.cliente.pk}/dashboard/")
        self.assertIn(esperado, html)

    def test_changelist_de_clientes_carrega(self):
        response = self.client.get(
            reverse("admin:clientes_cliente_changelist")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("clientes:dashboard_cliente", args=[self.cliente.pk]),
        )


class EditarClienteUITests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.cliente = Cliente.objects.create(nome="Cliente edicao")
        self.com_perm = User.objects.create_user(
            username="edit-cli",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "clientes.view_cliente",
            "clientes.change_cliente",
        )
        self.sem_perm = User.objects.create_user(
            username="sem-edit-cli",
            password="teste-123",
        )
        conceder_permissoes(self.sem_perm, "clientes.view_cliente")
        self.url = reverse("clientes:editar_cliente", args=[self.cliente.pk])

    def test_anonimo_redireciona_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_sem_permissao_recebe_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_com_permissao_get_e_post(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cliente-form-page")
        self.assertContains(response, 'id="id_endereco"')
        self.assertContains(response, 'id="id_observacoes"')
        self.assertContains(response, "cliente/css/cliente_form.css")
        self.assertContains(response, "cliente/js/cliente_form.js")
        self.assertContains(response, "Possui equipamento em comodato?")
        response = self.client.post(
            self.url,
            {
                "nome": "Cliente alterado",
                "cnpj": "",
                "telefone": "11999999999",
                "email": "",
                "endereco": "",
                "cidade": "São Paulo",
                "ativo": "on",
                "possui_equipamento_comodato": "False",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nome, "Cliente alterado")
        self.assertEqual(self.cliente.cidade, "São Paulo")
        self.assertFalse(self.cliente.possui_equipamento_comodato)


class CriarClienteUITests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="cria-cli",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "clientes.view_cliente",
            "clientes.add_cliente",
        )
        self.sem_perm = User.objects.create_user(
            username="sem-cria-cli",
            password="teste-123",
        )
        conceder_permissoes(self.sem_perm, "clientes.view_cliente")

    def test_sem_permissao_recebe_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("clientes:cadastrar_cliente"))
        self.assertEqual(response.status_code, 403)

    def test_cadastro_persiste(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("clientes:cadastrar_cliente"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cliente-form-page")
        self.assertContains(response, "Possui equipamento em comodato?")
        self.assertContains(response, "Ex.: João da Silva")
        self.assertContains(response, "Ex.: (14) 99999-9999")
        self.assertContains(response, "Ex.: contato@empresa.com.br")
        self.assertContains(response, "Ex.: Rua das Flores, 123")
        self.assertContains(response, "Ex.: Bauru")
        self.assertContains(response, "Ex.: 00.000.000/0000-00")
        response = self.client.post(
            reverse("clientes:cadastrar_cliente"),
            {
                "nome": "Cliente novo",
                "cnpj": "12.345.678/0001-99",
                "telefone": "",
                "email": "",
                "endereco": "",
                "cidade": "Campinas",
                "ativo": "on",
                "possui_equipamento_comodato": "True",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        cliente = Cliente.objects.get(nome="Cliente novo")
        self.assertEqual(cliente.cnpj, "12345678000199")
        self.assertEqual(cliente.cnpj_formatado, "12.345.678/0001-99")
        self.assertTrue(cliente.possui_equipamento_comodato)


class ClientesUrlNamespaceTests(TestCase):

    def test_rotas_resolvem_com_namespace(self):
        self.assertEqual(reverse("clientes:lista_clientes"), "/clientes/")
        self.assertEqual(reverse("clientes:cadastrar_cliente"), "/clientes/cadastrar/")
        self.assertEqual(
            reverse("clientes:editar_cliente", args=[7]),
            "/clientes/7/editar/",
        )
        self.assertEqual(
            reverse("clientes:dashboard_cliente", args=[7]),
            "/cliente/7/dashboard/",
        )

    def test_nomes_sem_namespace_nao_resolvem(self):
        with self.assertRaises(NoReverseMatch):
            reverse("dashboard_cliente", args=[7])


class ClienteDashboardCollapseJsTests(TestCase):

    def test_listeners_de_collapse_permanecem_ativos(self):
        js = (
            Path(settings.BASE_DIR)
            / "clientes"
            / "static"
            / "cliente"
            / "js"
            / "cliente_dashboard.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("once: true", js)
        self.assertIn("shown.bs.collapse", js)
        self.assertIn("hidden.bs.collapse", js)
        self.assertIn("aria-expanded", js)


class ClienteCnpjComodatoListaTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="lista-cli",
            password="teste-123",
        )
        conceder_permissoes(
            self.user,
            "clientes.view_cliente",
            "clientes.change_cliente",
        )
        self.client.force_login(self.user)

    def test_cnpj_armazenado_em_digitos_e_exibido_formatado(self):
        cliente = Cliente.objects.create(
            nome="Mercado Alfa",
            cnpj="11.222.333/0001-81",
        )
        self.assertEqual(cliente.cnpj, "11222333000181")
        self.assertEqual(cliente.cnpj_formatado, "11.222.333/0001-81")

        response = self.client.get(reverse("clientes:lista_clientes"))
        self.assertContains(response, "11.222.333/0001-81")
        self.assertNotContains(response, "11222333000181")

        dash = self.client.get(
            reverse("clientes:dashboard_cliente", args=[cliente.pk])
        )
        self.assertContains(dash, "11.222.333/0001-81")

    def test_listagem_ordem_alfabetica_e_indicador_comodato(self):
        sem_comodato = Cliente.objects.create(nome="Zeta Gelo")
        declarado = Cliente.objects.create(
            nome="Beta Gelo",
            possui_equipamento_comodato=True,
        )
        com_equipamento = Cliente.objects.create(
            nome="Alfa Gelo",
            possui_equipamento_comodato=False,
        )
        Equipamento.objects.create(
            nome="Freezer Alfa",
            tipo="freezer",
            cliente=com_equipamento,
        )

        response = self.client.get(reverse("clientes:lista_clientes"))
        self.assertEqual(response.status_code, 200)
        nomes = [cliente.nome for cliente in response.context["clientes"]]
        self.assertEqual(nomes, ["Alfa Gelo", "Beta Gelo", "Zeta Gelo"])
        self.assertContains(response, "Comodato")
        self.assertTrue(response.context["clientes"][0].possui_comodato_efetivo)
        self.assertTrue(declarado.possui_comodato_efetivo)
        self.assertFalse(sem_comodato.possui_comodato_efetivo)

    def test_edicao_nao_permite_marcar_nao_com_equipamento_vinculado(self):
        cliente = Cliente.objects.create(
            nome="Cliente com freezer",
            possui_equipamento_comodato=True,
        )
        Equipamento.objects.create(
            nome="Freezer vinculado",
            tipo="freezer",
            cliente=cliente,
        )
        url = reverse("clientes:editar_cliente", args=[cliente.pk])
        response = self.client.post(
            url,
            {
                "nome": "Cliente com freezer",
                "cnpj": "",
                "telefone": "",
                "email": "",
                "endereco": "",
                "cidade": "",
                "ativo": "on",
                "possui_equipamento_comodato": "False",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não é possível marcar Não")
        cliente.refresh_from_db()
        self.assertTrue(cliente.possui_equipamento_comodato)
