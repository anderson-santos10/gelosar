from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts.test_utils import conceder_permissoes
from clientes.models import Cliente
from equipamentos.models import ContratoComodato, Equipamento
from insumos.models import Insumo
from produtos.models import Produto


ADMIN_URLS = [
    "admin:index",
    "admin:login",
    "admin:clientes_cliente_changelist",
    "admin:vendas_venda_changelist",
    "admin:producao_producao_changelist",
    "admin:produtos_produto_changelist",
    "admin:insumos_insumo_changelist",
    "admin:equipamentos_equipamento_changelist",
    "admin:equipamentos_contratocomodato_changelist",
    "admin:auth_user_changelist",
    "admin:auth_group_changelist",
]


class GelosarAdminUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="gs-admin-super",
            password="teste-123",
        )
        self.staff = User.objects.create_user(
            username="gs-admin-staff",
            password="teste-123",
            is_staff=True,
        )

    def test_sidebar_urls_existem(self):
        for name in ADMIN_URLS:
            try:
                reverse(name)
            except NoReverseMatch as exc:
                self.fail(f"URL administrativa inválida: {name} ({exc})")

    def test_admin_exige_login(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_login_admin_funciona(self):
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": "gs-admin-super",
                "password": "teste-123",
                "next": reverse("admin:index"),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard administrativo")
        self.assertContains(response, "img/logo-gelosar.jpg")

    def test_superuser_ve_modulos(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:clientes_cliente_changelist"))
        self.assertContains(response, reverse("admin:equipamentos_equipamento_changelist"))
        self.assertContains(response, reverse("admin:vendas_venda_changelist"))
        self.assertContains(response, "Voltar ao sistema")
        self.assertContains(response, reverse("dashboard"))

    def test_staff_sem_permissao_nao_ve_modulo(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("admin:clientes_cliente_changelist"))
        blocked = self.client.get(reverse("admin:clientes_cliente_changelist"))
        self.assertEqual(blocked.status_code, 403)

    def test_staff_com_permissao_ve_clientes(self):
        conceder_permissoes(self.staff, "clientes.view_cliente")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, reverse("admin:clientes_cliente_changelist"))
        self.assertNotContains(response, reverse("admin:vendas_venda_changelist"))

    def test_dashboard_sem_dados(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("gs_dashboard_cards", response.context)
        values = [card["value"] for card in response.context["gs_dashboard_cards"]]
        self.assertTrue(all(value == 0 for value in values))

    def test_dashboard_com_dados(self):
        cliente = Cliente.objects.create(nome="Cliente admin ui")
        equipamento = Equipamento.objects.create(nome="Eq admin ui", tipo="freezer")
        ContratoComodato.objects.create(
            cliente=cliente,
            equipamento=equipamento,
            numero_contrato="ADM-UI-1",
            data_inicio="2026-01-01",
        )
        Produto.objects.create(nome="Gelo admin ui", peso_kg="5.00", preco_venda="10.00")
        Insumo.objects.create(nome="Insumo admin ui")
        Group.objects.create(name="Grupo admin ui")

        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        cards = {card["label"]: card["value"] for card in response.context["gs_dashboard_cards"]}
        self.assertEqual(cards["Clientes"], 1)
        self.assertEqual(cards["Equipamentos"], 1)
        self.assertEqual(cards["Contratos de comodato"], 1)

    def test_modeladmins_continuam_registrados(self):
        from django.contrib import admin

        from clientes.models import Cliente as ClienteModel
        from equipamentos.models import ContratoComodato as ContratoModel
        from equipamentos.models import Equipamento as EquipamentoModel
        from insumos.models import Insumo as InsumoModel
        from producao.models import Producao
        from produtos.models import ComposicaoProduto, Produto as ProdutoModel
        from vendas.models import Venda

        for model in (
            ClienteModel,
            EquipamentoModel,
            ContratoModel,
            ProdutoModel,
            ComposicaoProduto,
            InsumoModel,
            Producao,
            Venda,
        ):
            self.assertTrue(admin.site.is_registered(model), model)

    def test_changelist_clientes_continua_funcionando(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:clientes_cliente_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="q"')
