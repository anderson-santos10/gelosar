from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from produtos.models import Produto


class ProdutoUITests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="prod-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "produtos.view_produto",
            "produtos.add_produto",
            "produtos.change_produto",
        )
        self.sem_perm = User.objects.create_user(
            username="prod-sem",
            password="teste-123",
        )
        self.produto = Produto.objects.create(
            nome="Gelo UI",
            peso_kg="5.00",
            preco_venda="10.00",
        )

    def test_lista_anonimo_redireciona(self):
        response = self.client.get(reverse("produtos:lista_produtos"))
        self.assertEqual(response.status_code, 302)

    def test_lista_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("produtos:lista_produtos"))
        self.assertEqual(response.status_code, 403)

    def test_lista_com_permissao(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("produtos:lista_produtos"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gelo UI")

    def test_cadastro_persiste(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("produtos:cadastrar_produto"),
            {
                "nome": "Gelo 3kg UI",
                "peso_kg": "3.00",
                "preco_venda": "8.00",
                "estoque_minimo": "0",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Produto.objects.filter(nome="Gelo 3kg UI").exists())

    def test_edicao_persiste(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("produtos:editar_produto", args=[self.produto.pk]),
            {
                "nome": "Gelo UI editado",
                "peso_kg": "5.00",
                "preco_venda": "11.00",
                "estoque_minimo": "2",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.nome, "Gelo UI editado")
        self.assertEqual(self.produto.estoque_minimo, 2)

    def test_peso_duplicado_e_rejeitado(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("produtos:cadastrar_produto"),
            {
                "nome": "Gelo mesmo peso",
                "peso_kg": "5.00",
                "preco_venda": "9.00",
                "estoque_minimo": "0",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Produto.objects.filter(nome="Gelo mesmo peso").exists())
