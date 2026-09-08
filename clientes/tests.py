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
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nome, "Cliente alterado")
        self.assertEqual(self.cliente.cidade, "São Paulo")


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
        response = self.client.post(
            reverse("clientes:cadastrar_cliente"),
            {
                "nome": "Cliente novo",
                "cnpj": "",
                "telefone": "",
                "email": "",
                "endereco": "",
                "cidade": "Campinas",
                "ativo": "on",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Cliente.objects.filter(nome="Cliente novo").exists())


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
