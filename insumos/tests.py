from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from insumos.models import Insumo


class InsumoUITests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="ins-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "insumos.view_insumo",
            "insumos.add_insumo",
            "insumos.change_insumo",
        )
        self.sem_perm = User.objects.create_user(
            username="ins-sem",
            password="teste-123",
        )
        self.insumo = Insumo.objects.create(nome="Embalagem UI")

    def test_lista_anonimo_redireciona(self):
        response = self.client.get(reverse("insumos:lista_insumos"))
        self.assertEqual(response.status_code, 302)

    def test_lista_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("insumos:lista_insumos"))
        self.assertEqual(response.status_code, 403)

    def test_cadastro_e_edicao(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("insumos:lista_insumos"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("insumos:cadastrar_insumo"),
            {
                "nome": "Saco novo",
                "unidade": "un",
                "estoque_minimo": "0",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        criado = Insumo.objects.get(nome="Saco novo")
        response = self.client.post(
            reverse("insumos:editar_insumo", args=[criado.pk]),
            {
                "nome": "Saco novo",
                "unidade": "pc",
                "estoque_minimo": "5",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        criado.refresh_from_db()
        self.assertEqual(criado.unidade, "pc")
        self.assertEqual(criado.estoque_minimo, 5)
