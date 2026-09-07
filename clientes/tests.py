from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente


class DashboardClienteViewTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cliente-dash",
            password="teste-123",
        )
        self.cliente = Cliente.objects.create(nome="Cliente dashboard")
        self.client.force_login(self.user)

    def test_dashboard_cliente_carrega_sem_historico(self):
        response = self.client.get(
            reverse("dashboard_cliente", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("chart_compras_mes", response.context)
        self.assertIn("chart_produtos", response.context)
        self.assertContains(response, "cliente_dashboard.js")
        self.assertContains(response, 'data-gs-sensitive')
        self.assertNotContains(response, "onclick=")
