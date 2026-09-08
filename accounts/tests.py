from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from clientes.models import Cliente
from equipamentos.models import Equipamento


class AutorizacaoModuloTests(TestCase):
    """ALTO-006: autenticação ≠ autorização; acesso direto à URL."""

    def setUp(self):
        User = get_user_model()
        self.User = User
        self.sem_perm = User.objects.create_user(
            username="sem-perm",
            password="teste-123",
        )
        self.com_perm = User.objects.create_user(
            username="com-perm",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "estoque.view_movimentacaoproduto",
            "clientes.view_cliente",
            "equipamentos.view_equipamento",
        )
        self.superuser = User.objects.create_superuser(
            username="authz-super",
            password="teste-123",
        )
        self.cliente = Cliente.objects.create(nome="Cliente authz")
        self.equipamento = Equipamento.objects.create(
            nome="Equipamento authz",
            tipo="maquina_gelo",
        )
        self.url_estoque = reverse("estoque:estoque")
        self.url_cliente_pk = reverse(
            "clientes:dashboard_cliente",
            args=[self.cliente.pk],
        )
        self.url_equipamento_pk = reverse(
            "equipamentos:detalhe_equipamento",
            args=[self.equipamento.pk],
        )

    def test_nao_autenticado_e_redirecionado_ao_login(self):
        response = self.client.get(self.url_estoque)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_autenticado_sem_permissao_recebe_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(self.url_estoque)
        self.assertEqual(response.status_code, 403)

    def test_autenticado_com_permissao_acessa(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(self.url_estoque)
        self.assertEqual(response.status_code, 200)

    def test_superuser_acessa_area_protegida(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.url_estoque)
        self.assertEqual(response.status_code, 200)

    def test_url_com_pk_sem_permissao_recebe_403(self):
        self.client.force_login(self.sem_perm)
        response_cliente = self.client.get(self.url_cliente_pk)
        response_equipamento = self.client.get(self.url_equipamento_pk)
        self.assertEqual(response_cliente.status_code, 403)
        self.assertEqual(response_equipamento.status_code, 403)

    def test_url_com_pk_com_permissao_acessa(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(self.url_cliente_pk)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.url_equipamento_pk)
        self.assertEqual(response.status_code, 200)


class LoginMarcaTests(TestCase):

    def test_login_referencia_logo_existente(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "img/logo-gelosar.jpg")
        self.assertContains(response, "GELOSAR")
