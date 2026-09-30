from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from core.periodo import dia_local_atual
from equipamentos.validators import MENSAGEM_TAMANHO_EXCEDIDO, TAMANHO_MAXIMO_BYTES
from financeiro.admin import ContaPagarAdmin
from financeiro.forms import ContaPagarForm, ContaRecorrenteForm
from financeiro.models import CategoriaFinanceira, ContaPagar, ContaRecorrente, Fornecedor
from financeiro.services.recorrentes import gerar_competencia, gerar_conta_recorrente
from financeiro.tests_veiculos import criar_veiculo


class FornecedorModelTests(TestCase):
    def test_criacao_valida_sem_cnpj(self):
        fornecedor = Fornecedor.objects.create(nome="Energia Local")
        self.assertTrue(fornecedor.ativo)
        self.assertIsNone(fornecedor.cnpj)

    def test_cnpj_armazenado_somente_digitos(self):
        fornecedor = Fornecedor.objects.create(
            nome="Fornecedor CNPJ",
            cnpj="12.345.678/0001-99",
        )
        self.assertEqual(fornecedor.cnpj, "12345678000199")
        self.assertEqual(fornecedor.cnpj_formatado, "12.345.678/0001-99")

    def test_varios_fornecedores_sem_cnpj(self):
        Fornecedor.objects.create(nome="A")
        Fornecedor.objects.create(nome="B")
        self.assertEqual(Fornecedor.objects.filter(cnpj__isnull=True).count(), 2)

    def test_cnpj_duplicado_e_rejeitado(self):
        Fornecedor.objects.create(nome="Um", cnpj="12345678000199")
        with self.assertRaises(IntegrityError):
            Fornecedor.objects.create(nome="Dois", cnpj="12.345.678/0001-99")

    def test_full_clean_rejeita_digitos_invalidos(self):
        fornecedor = Fornecedor(nome="Curto", cnpj="123")
        with self.assertRaises(ValidationError):
            fornecedor.full_clean()
        cpf_ok = Fornecedor(nome="Pessoa", cnpj="12345678901")
        cpf_ok.full_clean()


class CategoriaFinanceiraModelTests(TestCase):
    def test_criacao_gera_slug_e_defaults(self):
        categoria = CategoriaFinanceira.objects.create(nome="Taxa extra", ordem=200)
        self.assertEqual(categoria.slug, "taxa-extra")
        self.assertEqual(categoria.tipo, CategoriaFinanceira.TIPO_DESPESA)
        self.assertTrue(categoria.ativo)
        self.assertFalse(categoria.exige_veiculo)

    def test_slug_unico(self):
        CategoriaFinanceira.objects.create(nome="Aluguel 2", slug="aluguel-2")
        with self.assertRaises(IntegrityError):
            CategoriaFinanceira.objects.create(nome="Outro", slug="aluguel-2")

    def test_seed_inicial_presente(self):
        slugs = set(
            CategoriaFinanceira.objects.values_list("slug", flat=True)
        )
        self.assertIn("impostos", slugs)
        self.assertIn("combustivel", slugs)
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        veiculos = CategoriaFinanceira.objects.get(slug="veiculos")
        manutencao = CategoriaFinanceira.objects.get(slug="manutencao")
        self.assertTrue(combustivel.exige_veiculo)
        self.assertTrue(veiculos.exige_veiculo)
        self.assertFalse(manutencao.exige_veiculo)
        self.assertTrue(
            CategoriaFinanceira.objects.filter(tipo="despesa", ativo=True).count() >= 16
        )



class FornecedorUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="fin-forn-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "financeiro.view_fornecedor",
            "financeiro.add_fornecedor",
            "financeiro.change_fornecedor",
        )
        self.sem_perm = User.objects.create_user(
            username="fin-forn-sem",
            password="teste-123",
        )
        self.fornecedor = Fornecedor.objects.create(nome="Fornecedor UI")

    def test_lista_anonimo_redireciona(self):
        response = self.client.get(reverse("financeiro:lista_fornecedores"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_lista_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("financeiro:lista_fornecedores"))
        self.assertEqual(response.status_code, 403)

    def test_lista_com_permissao(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:lista_fornecedores"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fornecedor UI")
        self.assertContains(response, "Financeiro")

    def test_cadastro_persiste_cnpj_formatado(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_fornecedor"),
            {
                "nome": "Novo Fornecedor",
                "cnpj": "12.345.678/0001-99",
                "telefone": "11988887777",
                "email": "a@b.com",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        criado = Fornecedor.objects.get(nome="Novo Fornecedor")
        self.assertEqual(criado.cnpj, "12345678000199")

        lista = self.client.get(reverse("financeiro:lista_fornecedores"))
        self.assertContains(lista, "12.345.678/0001-99")
        self.assertNotContains(lista, "12345678000199")

    def test_cnpj_invalido_e_rejeitado(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_fornecedor"),
            {
                "nome": "Inválido",
                "cnpj": "123",
                "telefone": "",
                "email": "",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "14 dígitos")
        self.assertFalse(Fornecedor.objects.filter(nome="Inválido").exists())

    def test_cpf_com_tamanho_invalido_rejeitado(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_fornecedor"),
            {
                "nome": "CPF curto",
                "cnpj": "1234567890",
                "telefone": "",
                "email": "",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Fornecedor.objects.filter(nome="CPF curto").exists())

    def test_cnpj_duplicado_no_formulario(self):
        Fornecedor.objects.create(nome="Existente", cnpj="12345678000199")
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_fornecedor"),
            {
                "nome": "Cópia",
                "cnpj": "12345678000199",
                "telefone": "",
                "email": "",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Já existe um fornecedor")

    def test_edicao_e_alternar_ativo(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:editar_fornecedor", args=[self.fornecedor.pk]),
            {
                "nome": "Fornecedor editado",
                "cnpj": "",
                "telefone": "1133334444",
                "email": "",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.fornecedor.refresh_from_db()
        self.assertEqual(self.fornecedor.nome, "Fornecedor editado")

        response = self.client.post(
            reverse("financeiro:alternar_ativo_fornecedor", args=[self.fornecedor.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.fornecedor.refresh_from_db()
        self.assertFalse(self.fornecedor.ativo)


class CategoriaUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="fin-cat-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "financeiro.view_categoriafinanceira",
            "financeiro.add_categoriafinanceira",
            "financeiro.change_categoriafinanceira",
        )
        self.sem_perm = User.objects.create_user(
            username="fin-cat-sem",
            password="teste-123",
        )

    def test_lista_anonimo_redireciona(self):
        response = self.client.get(reverse("financeiro:lista_categorias"))
        self.assertEqual(response.status_code, 302)

    def test_lista_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("financeiro:lista_categorias"))
        self.assertEqual(response.status_code, 403)

    def test_lista_com_permissao_mostra_seed(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:lista_categorias"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Energia elétrica")
        self.assertContains(response, "Exige veículo")

    def test_cadastro_gera_slug_e_tipo(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_categoria"),
            {
                "nome": "Taxa portuária extra",
                "slug": "",
                "tipo": "despesa",
                "ordem": "170",
                "exige_veiculo": "on",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        categoria = CategoriaFinanceira.objects.get(nome="Taxa portuária extra")
        self.assertEqual(categoria.slug, "taxa-portuaria-extra")
        self.assertTrue(categoria.exige_veiculo)
        self.assertEqual(categoria.tipo, "despesa")

    def test_slug_duplicado_no_formulario(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_categoria"),
            {
                "nome": "Impostos 2",
                "slug": "impostos",
                "tipo": "despesa",
                "ordem": "5",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Já existe uma categoria")

    def test_edicao_e_alternar_ativo(self):
        categoria = CategoriaFinanceira.objects.get(slug="outros")
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:editar_categoria", args=[categoria.pk]),
            {
                "nome": "Outros custos",
                "slug": "outros",
                "tipo": "despesa",
                "ordem": "160",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        categoria.refresh_from_db()
        self.assertEqual(categoria.nome, "Outros custos")

        response = self.client.post(
            reverse("financeiro:alternar_ativo_categoria", args=[categoria.pk])
        )
        self.assertEqual(response.status_code, 302)
        categoria.refresh_from_db()
        self.assertFalse(categoria.ativo)

    def test_alternar_ativo_sem_permissao_403(self):
        categoria = CategoriaFinanceira.objects.get(slug="aluguel")
        self.client.force_login(self.sem_perm)
        response = self.client.post(
            reverse("financeiro:alternar_ativo_categoria", args=[categoria.pk])
        )
        self.assertEqual(response.status_code, 403)


def _conta(categoria, **kwargs):
    hoje = dia_local_atual()
    dados = {
        "descricao": "Conta teste",
        "categoria": categoria,
        "competencia": hoje.replace(day=1),
        "valor": Decimal("100.00"),
        "data_vencimento": hoje,
        "status": ContaPagar.STATUS_PENDENTE,
    }
    dados.update(kwargs)
    return ContaPagar.objects.create(**dados)


def _payload_edicao(conta, **overrides):
    dados = {
        "descricao": conta.descricao,
        "categoria": conta.categoria_id,
        "fornecedor": conta.fornecedor_id or "",
        "competencia": conta.competencia.isoformat(),
        "valor": str(conta.valor),
        "data_vencimento": conta.data_vencimento.isoformat(),
        "status": conta.status,
        "forma_pagamento": conta.forma_pagamento,
        "observacoes": conta.observacoes,
    }
    if conta.data_emissao:
        dados["data_emissao"] = conta.data_emissao.isoformat()
    if conta.data_pagamento:
        dados["data_pagamento"] = conta.data_pagamento.isoformat()
    dados.update(overrides)
    return dados


class ContaPagarModelTests(TestCase):
    def setUp(self):
        self.categoria = CategoriaFinanceira.objects.get(slug="aluguel")
        self.hoje = dia_local_atual()

    def test_criacao_valida(self):
        conta = _conta(self.categoria, descricao="Aluguel março")
        self.assertEqual(conta.status, ContaPagar.STATUS_PENDENTE)
        self.assertFalse(conta.vencida)
        self.assertEqual(conta.status_display_financeiro, "Pendente")

    def test_valor_zero_e_negativo_invalidos(self):
        conta_zero = _conta(self.categoria, valor=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            conta_zero.full_clean()
        conta_neg = _conta(self.categoria, descricao="Negativa", valor=Decimal("-10.00"))
        with self.assertRaises(ValidationError):
            conta_neg.full_clean()

    def test_vencida_somente_pendente_atrasada(self):
        futura = _conta(
            self.categoria,
            descricao="Futura",
            data_vencimento=self.hoje + timedelta(days=5),
        )
        atrasada = _conta(
            self.categoria,
            descricao="Atrasada",
            data_vencimento=self.hoje - timedelta(days=1),
        )
        paga = _conta(
            self.categoria,
            descricao="Paga atrasada",
            data_vencimento=self.hoje - timedelta(days=1),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=self.hoje,
        )
        cancelada = _conta(
            self.categoria,
            descricao="Cancelada atrasada",
            data_vencimento=self.hoje - timedelta(days=1),
            status=ContaPagar.STATUS_CANCELADO,
        )
        self.assertFalse(futura.vencida)
        self.assertTrue(atrasada.vencida)
        self.assertEqual(atrasada.status_display_financeiro, "Vencida")
        self.assertFalse(paga.vencida)
        self.assertFalse(cancelada.vencida)

    def test_pago_exige_data_pagamento(self):
        conta = _conta(self.categoria, status=ContaPagar.STATUS_PAGO)
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def test_pendente_nao_pode_ter_pagamento(self):
        conta = _conta(
            self.categoria,
            data_pagamento=self.hoje,
        )
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def test_cancelado_sem_pagamento_e_valido(self):
        conta = _conta(
            self.categoria,
            status=ContaPagar.STATUS_CANCELADO,
        )
        conta.full_clean()

    def test_pagamento_anterior_a_emissao_invalido(self):
        conta = _conta(
            self.categoria,
            data_emissao=self.hoje,
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=self.hoje - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def test_pendente_pode_alterar_valor(self):
        conta = _conta(self.categoria, descricao="Editável")
        conta.valor = Decimal("180.00")
        conta.full_clean()
        conta.save()
        conta.refresh_from_db()
        self.assertEqual(conta.valor, Decimal("180.00"))

    def test_paga_nao_pode_alterar_nem_reabrir(self):
        conta = _conta(
            self.categoria,
            descricao="Paga fechada",
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=self.hoje,
            valor=Decimal("100.00"),
        )
        conta.valor = Decimal("1.00")
        with self.assertRaises(ValidationError):
            conta.full_clean()
        conta.status = ContaPagar.STATUS_PENDENTE
        conta.data_pagamento = None
        with self.assertRaises(ValidationError):
            conta.save()
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(conta.valor, Decimal("100.00"))
        self.assertEqual(conta.data_pagamento, self.hoje)

    def test_cancelada_nao_pode_alterar_nem_reabrir(self):
        conta = _conta(
            self.categoria,
            descricao="Cancelada fechada",
            status=ContaPagar.STATUS_CANCELADO,
            valor=Decimal("100.00"),
        )
        conta.valor = Decimal("50.00")
        with self.assertRaises(ValidationError):
            conta.full_clean()
        conta.status = ContaPagar.STATUS_PENDENTE
        with self.assertRaises(ValidationError):
            conta.save()
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_CANCELADO)
        self.assertEqual(conta.valor, Decimal("100.00"))


class ContaPagarFormTests(TestCase):
    def setUp(self):
        self.categoria = CategoriaFinanceira.objects.get(slug="energia-eletrica")
        self.fornecedor = Fornecedor.objects.create(
            nome="CPFL",
            cnpj="12.345.678/0001-99",
        )
        self.inativa = CategoriaFinanceira.objects.create(
            nome="Cat inativa",
            slug="cat-inativa-form",
            ativo=False,
        )
        self.fornecedor_inativo = Fornecedor.objects.create(
            nome="Inativo Ltda",
            ativo=False,
        )

    def test_queryset_mostra_apenas_ativos_em_cadastro(self):
        form = ContaPagarForm()
        self.assertIn(self.categoria, form.fields["categoria"].queryset)
        self.assertNotIn(self.inativa, form.fields["categoria"].queryset)
        self.assertIn(self.fornecedor, form.fields["fornecedor"].queryset)
        self.assertNotIn(self.fornecedor_inativo, form.fields["fornecedor"].queryset)

    def test_edicao_mantem_vinculo_inativo(self):
        conta = _conta(self.inativa, fornecedor=self.fornecedor_inativo)
        form = ContaPagarForm(instance=conta)
        self.assertIn(self.inativa, form.fields["categoria"].queryset)
        self.assertIn(self.fornecedor_inativo, form.fields["fornecedor"].queryset)

    def test_formulario_rejeita_conta_paga(self):
        conta = _conta(
            self.categoria,
            fornecedor=self.fornecedor,
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=dia_local_atual(),
        )
        form = ContaPagarForm(
            data=_payload_edicao(conta, valor="9.99"),
            instance=conta,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            ContaPagar.MENSAGEM_LANCAMENTO_FECHADO,
            form.non_field_errors(),
        )

    def test_formulario_rejeita_conta_cancelada(self):
        conta = _conta(
            self.categoria,
            fornecedor=self.fornecedor,
            status=ContaPagar.STATUS_CANCELADO,
        )
        form = ContaPagarForm(
            data=_payload_edicao(
                conta,
                status=ContaPagar.STATUS_PENDENTE,
                categoria=self.categoria.pk,
            ),
            instance=conta,
        )
        self.assertFalse(form.is_valid())

    def test_valor_invalido_no_formulario(self):
        form = ContaPagarForm(
            data={
                "descricao": "Inválida",
                "categoria": self.categoria.pk,
                "competencia": "2026-03-01",
                "valor": "0",
                "data_vencimento": "2026-03-10",
                "status": ContaPagar.STATUS_PENDENTE,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("valor", form.errors)


class ContaPagarViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.categoria = CategoriaFinanceira.objects.get(slug="impostos")
        self.fornecedor = Fornecedor.objects.create(nome="Prefeitura")
        self.com_perm = User.objects.create_user(
            username="fin-cp-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "financeiro.view_contapagar",
            "financeiro.add_contapagar",
            "financeiro.change_contapagar",
        )
        self.sem_perm = User.objects.create_user(
            username="fin-cp-sem",
            password="teste-123",
        )
        self.hoje = dia_local_atual()
        self.conta = _conta(
            self.categoria,
            descricao="IPTU",
            fornecedor=self.fornecedor,
            valor=Decimal("250.00"),
            data_vencimento=self.hoje - timedelta(days=2),
        )

    def test_lista_anonimo_redireciona(self):
        response = self.client.get(reverse("financeiro:lista_contas_pagar"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_lista_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("financeiro:lista_contas_pagar"))
        self.assertEqual(response.status_code, 403)

    def test_lista_com_permissao_mostra_vencida(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:lista_contas_pagar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IPTU")
        self.assertContains(response, "Vencida")
        self.assertContains(response, "Contas a pagar")

    def test_cadastro_preenche_criado_por(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            {
                "descricao": "Conta nova",
                "categoria": self.categoria.pk,
                "fornecedor": self.fornecedor.pk,
                "competencia": self.hoje.replace(day=1).isoformat(),
                "valor": "80.50",
                "data_vencimento": self.hoje.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
                "forma_pagamento": "",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        criada = ContaPagar.objects.get(descricao="Conta nova")
        self.assertEqual(criada.criado_por, self.com_perm)
        self.assertEqual(criada.valor, Decimal("80.50"))

    def test_edicao_com_permissao(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:editar_conta_pagar", args=[self.conta.pk]),
            {
                "descricao": "IPTU atualizado",
                "categoria": self.categoria.pk,
                "fornecedor": self.fornecedor.pk,
                "competencia": self.conta.competencia.isoformat(),
                "valor": "250.00",
                "data_vencimento": self.conta.data_vencimento.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
                "observacoes": "ok",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.descricao, "IPTU atualizado")

    def test_lista_esconde_editar_de_lancamento_fechado(self):
        paga = _conta(
            self.categoria,
            descricao="Conta já paga",
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=self.hoje,
        )
        cancelada = _conta(
            self.categoria,
            descricao="Conta já cancelada",
            status=ContaPagar.STATUS_CANCELADO,
        )
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:lista_contas_pagar"))
        self.assertContains(response, "Conta paga — edição bloqueada")
        self.assertContains(response, "Conta cancelada — edição bloqueada")
        self.assertContains(
            response,
            reverse("financeiro:editar_conta_pagar", args=[self.conta.pk]),
        )
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_pagar", args=[paga.pk]),
        )
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_pagar", args=[cancelada.pk]),
        )

    def test_get_edicao_paga_403(self):
        conta = _conta(
            self.categoria,
            descricao="Paga GET",
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=self.hoje,
        )
        self.client.force_login(self.com_perm)
        response = self.client.get(
            reverse("financeiro:editar_conta_pagar", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_post_edicao_paga_rejeitado(self):
        original = self.hoje - timedelta(days=3)
        outra = CategoriaFinanceira.objects.get(slug="aluguel")
        conta = _conta(
            self.categoria,
            descricao="Paga POST",
            fornecedor=self.fornecedor,
            valor=Decimal("250.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=original,
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:editar_conta_pagar", args=[conta.pk]),
            _payload_edicao(
                conta,
                descricao="Tentativa",
                valor="1.00",
                status=ContaPagar.STATUS_PENDENTE,
                data_pagamento="",
                categoria=outra.pk,
                fornecedor="",
            ),
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.descricao, "Paga POST")
        self.assertEqual(conta.valor, Decimal("250.00"))
        self.assertEqual(conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(conta.data_pagamento, original)
        self.assertEqual(conta.categoria_id, self.categoria.pk)
        self.assertEqual(conta.fornecedor_id, self.fornecedor.pk)

    def test_get_edicao_cancelada_403(self):
        conta = _conta(
            self.categoria,
            descricao="Cancelada GET",
            status=ContaPagar.STATUS_CANCELADO,
        )
        self.client.force_login(self.com_perm)
        response = self.client.get(
            reverse("financeiro:editar_conta_pagar", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_post_edicao_cancelada_rejeitado(self):
        outra = CategoriaFinanceira.objects.get(slug="aluguel")
        conta = _conta(
            self.categoria,
            descricao="Cancelada POST",
            fornecedor=self.fornecedor,
            valor=Decimal("80.00"),
            status=ContaPagar.STATUS_CANCELADO,
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:editar_conta_pagar", args=[conta.pk]),
            _payload_edicao(
                conta,
                valor="10.00",
                status=ContaPagar.STATUS_PENDENTE,
                categoria=outra.pk,
                fornecedor="",
            ),
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.valor, Decimal("80.00"))
        self.assertEqual(conta.status, ContaPagar.STATUS_CANCELADO)
        self.assertEqual(conta.categoria_id, self.categoria.pk)
        self.assertEqual(conta.fornecedor_id, self.fornecedor.pk)

    def test_marcar_paga_somente_post(self):
        self.client.force_login(self.com_perm)
        url = reverse("financeiro:marcar_conta_paga", args=[self.conta.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(self.conta.data_pagamento, self.hoje)
        self.assertEqual(self.conta.valor, Decimal("250.00"))

    def test_cancelar_somente_post(self):
        self.client.force_login(self.com_perm)
        url = reverse("financeiro:cancelar_conta_pagar", args=[self.conta.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, ContaPagar.STATUS_CANCELADO)
        self.assertTrue(ContaPagar.objects.filter(pk=self.conta.pk).exists())

    def test_acoes_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        self.assertEqual(
            self.client.post(
                reverse("financeiro:marcar_conta_paga", args=[self.conta.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("financeiro:cancelar_conta_pagar", args=[self.conta.pk])
            ).status_code,
            403,
        )

    def test_pendente_para_paga(self):
        conta = _conta(
            self.categoria,
            descricao="Pendente a pagar",
            data_vencimento=self.hoje + timedelta(days=5),
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:marcar_conta_paga", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(conta.data_pagamento, self.hoje)

    def test_vencida_para_paga(self):
        self.assertTrue(self.conta.vencida)
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:marcar_conta_paga", args=[self.conta.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(self.conta.data_pagamento, self.hoje)

    def test_pendente_para_cancelada(self):
        conta = _conta(
            self.categoria,
            descricao="Pendente a cancelar",
            data_vencimento=self.hoje + timedelta(days=3),
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cancelar_conta_pagar", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_CANCELADO)
        self.assertIsNone(conta.data_pagamento)

    def test_paga_para_paga_preserva_data(self):
        original = self.hoje - timedelta(days=10)
        conta = _conta(
            self.categoria,
            descricao="Já paga",
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=original,
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:marcar_conta_paga", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(conta.data_pagamento, original)

    def test_paga_nao_pode_cancelar(self):
        original = self.hoje - timedelta(days=4)
        conta = _conta(
            self.categoria,
            descricao="Paga protegida",
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=original,
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cancelar_conta_pagar", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(conta.data_pagamento, original)

    def test_cancelada_nao_pode_marcar_paga(self):
        conta = _conta(
            self.categoria,
            descricao="Cancelada protegida",
            status=ContaPagar.STATUS_CANCELADO,
            data_pagamento=None,
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:marcar_conta_paga", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_CANCELADO)
        self.assertIsNone(conta.data_pagamento)

    def test_cancelada_para_cancelada(self):
        conta = _conta(
            self.categoria,
            descricao="Já cancelada",
            status=ContaPagar.STATUS_CANCELADO,
        )
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cancelar_conta_pagar", args=[conta.pk])
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaPagar.STATUS_CANCELADO)
        self.assertIsNone(conta.data_pagamento)

    def test_post_exige_veiculo_sem_veiculo(self):
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            {
                "descricao": "Gasolina",
                "categoria": combustivel.pk,
                "competencia": self.hoje.replace(day=1).isoformat(),
                "valor": "120.00",
                "data_vencimento": self.hoje.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContaPagar.objects.filter(descricao="Gasolina").exists())

    def test_post_exige_veiculo_com_veiculo(self):
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        veiculo = criar_veiculo()
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            {
                "descricao": "Gasolina ok",
                "categoria": combustivel.pk,
                "competencia": self.hoje.replace(day=1).isoformat(),
                "valor": "120.00",
                "data_vencimento": self.hoje.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
                "veiculo": veiculo.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        conta = ContaPagar.objects.get(descricao="Gasolina ok")
        self.assertEqual(conta.veiculo_id, veiculo.pk)

    def test_anexo_acima_do_limite(self):
        from io import BytesIO

        from django.core.files.uploadedfile import InMemoryUploadedFile

        arquivo = InMemoryUploadedFile(
            BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"),
            "anexo",
            "nota.pdf",
            "application/pdf",
            TAMANHO_MAXIMO_BYTES + 1,
            None,
        )
        form = ContaPagarForm(
            data={
                "descricao": "Com anexo",
                "categoria": self.categoria.pk,
                "competencia": self.hoje.replace(day=1).isoformat(),
                "valor": "10.00",
                "data_vencimento": self.hoje.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
            },
            files={"anexo": arquivo},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("anexo", form.errors)
        self.assertIn(MENSAGEM_TAMANHO_EXCEDIDO, form.errors["anexo"][0])


class ContaPagarAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.hoje = dia_local_atual()
        self.categoria = CategoriaFinanceira.objects.get(slug="impostos")
        self.admin_user = User.objects.create_superuser(
            username="fin-admin-cp",
            password="teste-123",
        )
        self.factory = RequestFactory()
        self.model_admin = ContaPagarAdmin(ContaPagar, AdminSite())

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.admin_user
        return request

    def test_pendente_continua_editavel_no_admin(self):
        conta = _conta(self.categoria, descricao="Admin pendente")
        request = self._request()
        self.assertTrue(self.model_admin.has_change_permission(request, conta))
        self.assertTrue(self.model_admin.has_delete_permission(request, conta))
        self.client.force_login(self.admin_user)
        url = reverse("admin:financeiro_contapagar_change", args=[conta.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(
            url,
            {
                "descricao": "Admin pendente editada",
                "categoria": self.categoria.pk,
                "competencia": conta.competencia.isoformat(),
                "valor": "111.00",
                "data_vencimento": conta.data_vencimento.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
                "observacoes": "",
                "forma_pagamento": "",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.descricao, "Admin pendente editada")
        self.assertEqual(conta.valor, Decimal("111.00"))

    def test_paga_protegida_no_admin(self):
        conta = _conta(
            self.categoria,
            descricao="Admin paga",
            valor=Decimal("200.00"),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=self.hoje,
        )
        request = self._request()
        self.assertFalse(self.model_admin.has_change_permission(request, conta))
        self.assertFalse(self.model_admin.has_delete_permission(request, conta))
        self.client.force_login(self.admin_user)
        url = reverse("admin:financeiro_contapagar_change", args=[conta.pk])
        response = self.client.post(
            url,
            {
                "descricao": "Admin paga alterada",
                "categoria": self.categoria.pk,
                "competencia": conta.competencia.isoformat(),
                "valor": "1.00",
                "data_vencimento": conta.data_vencimento.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
                "observacoes": "",
                "forma_pagamento": "",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.descricao, "Admin paga")
        self.assertEqual(conta.valor, Decimal("200.00"))
        self.assertEqual(conta.status, ContaPagar.STATUS_PAGO)
        self.assertEqual(conta.data_pagamento, self.hoje)

    def test_cancelada_protegida_no_admin(self):
        conta = _conta(
            self.categoria,
            descricao="Admin cancelada",
            valor=Decimal("75.00"),
            status=ContaPagar.STATUS_CANCELADO,
        )
        request = self._request()
        self.assertFalse(self.model_admin.has_change_permission(request, conta))
        self.assertFalse(self.model_admin.has_delete_permission(request, conta))
        self.client.force_login(self.admin_user)
        url = reverse("admin:financeiro_contapagar_change", args=[conta.pk])
        response = self.client.post(
            url,
            {
                "descricao": "Admin cancelada alterada",
                "categoria": self.categoria.pk,
                "competencia": conta.competencia.isoformat(),
                "valor": "2.00",
                "data_vencimento": conta.data_vencimento.isoformat(),
                "status": ContaPagar.STATUS_PENDENTE,
                "observacoes": "",
                "forma_pagamento": "",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.descricao, "Admin cancelada")
        self.assertEqual(conta.valor, Decimal("75.00"))
        self.assertEqual(conta.status, ContaPagar.STATUS_CANCELADO)


class ContaPagarFiltroTotaisTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="fin-filtro",
            password="teste-123",
        )
        conceder_permissoes(self.user, "financeiro.view_contapagar")
        self.client.force_login(self.user)
        self.aluguel = CategoriaFinanceira.objects.get(slug="aluguel")
        self.energia = CategoriaFinanceira.objects.get(slug="energia-eletrica")
        self.forn_a = Fornecedor.objects.create(nome="Imobiliária Alfa")
        self.forn_b = Fornecedor.objects.create(nome="CPFL Energia")
        hoje = dia_local_atual()
        self.hoje = hoje
        _conta(
            self.aluguel,
            descricao="Aluguel loja",
            fornecedor=self.forn_a,
            valor=Decimal("1000.00"),
            competencia=hoje.replace(day=1),
            data_vencimento=hoje + timedelta(days=10),
            observacoes="contrato anual",
        )
        _conta(
            self.aluguel,
            descricao="Aluguel atrasado",
            fornecedor=self.forn_a,
            valor=Decimal("200.00"),
            competencia=hoje.replace(day=1),
            data_vencimento=hoje - timedelta(days=3),
        )
        _conta(
            self.energia,
            descricao="Energia paga",
            fornecedor=self.forn_b,
            valor=Decimal("300.00"),
            competencia=hoje.replace(day=1),
            status=ContaPagar.STATUS_PAGO,
            data_pagamento=hoje,
        )
        _conta(
            self.energia,
            descricao="Taxa cancelada",
            fornecedor=self.forn_b,
            valor=Decimal("50.00"),
            competencia=hoje.replace(month=1, day=1) if hoje.month != 1 else hoje.replace(year=hoje.year - 1, month=1, day=1),
            status=ContaPagar.STATUS_CANCELADO,
        )

    def test_totais_gerais(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("financeiro:lista_contas_pagar"))
        totais = response.context["totais"]
        self.assertEqual(totais["total_pendente"], Decimal("1200.00"))
        self.assertEqual(totais["total_vencido"], Decimal("200.00"))
        self.assertEqual(totais["total_pago"], Decimal("300.00"))
        self.assertEqual(totais["total_geral"], Decimal("1550.00"))

    def test_filtro_status_vencida(self):
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {"status": "vencida"},
        )
        nomes = [conta.descricao for conta in response.context["contas"]]
        self.assertEqual(nomes, ["Aluguel atrasado"])

    def test_filtro_status_pendente_nao_inclui_vencida(self):
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {"status": "pendente"},
        )
        nomes = [conta.descricao for conta in response.context["contas"]]
        self.assertEqual(nomes, ["Aluguel loja"])

    def test_filtro_categoria_fornecedor_busca_periodo(self):
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {
                "categoria": str(self.aluguel.pk),
                "fornecedor": str(self.forn_a.pk),
                "q": "loja",
                "competencia_inicio": self.hoje.replace(day=1).isoformat(),
                "competencia_fim": self.hoje.isoformat(),
            },
        )
        nomes = [conta.descricao for conta in response.context["contas"]]
        self.assertEqual(nomes, ["Aluguel loja"])
        self.assertEqual(response.context["totais"]["total_geral"], Decimal("1000.00"))

    def test_paginacao_preserva_filtros(self):
        for indice in range(26):
            _conta(
                self.energia,
                descricao=f"Lote extra {indice:02d}",
                valor=Decimal("1.00"),
                data_vencimento=self.hoje + timedelta(days=20),
            )
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {"q": "Lote extra", "page": "2"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["page_obj"].has_previous())
        self.assertIn("q=Lote+extra", response.context["filtro_querystring"])
        self.assertContains(response, "page=1")
        self.assertContains(response, "Lote extra")

    def test_busca_por_descricao_fornecedor_e_observacao(self):
        lista = reverse("financeiro:lista_contas_pagar")
        por_descricao = self.client.get(lista, {"q": "loja"})
        self.assertEqual(
            [conta.descricao for conta in por_descricao.context["contas"]],
            ["Aluguel loja"],
        )
        por_fornecedor = self.client.get(lista, {"q": "imobiliária"})
        nomes = [conta.descricao for conta in por_fornecedor.context["contas"]]
        self.assertIn("Aluguel loja", nomes)
        self.assertIn("Aluguel atrasado", nomes)
        por_obs = self.client.get(lista, {"q": "CONTRATO ANUAL"})
        self.assertEqual(
            [conta.descricao for conta in por_obs.context["contas"]],
            ["Aluguel loja"],
        )

    def test_busca_sem_resultados(self):
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {"q": "xyz-inexistente"},
        )
        self.assertEqual(list(response.context["contas"]), [])
        self.assertContains(response, "Nenhuma conta encontrada")
        self.assertContains(
            response,
            "Não encontramos contas que correspondam aos filtros selecionados.",
        )

    def test_filtro_status_pago_e_cancelado(self):
        lista = reverse("financeiro:lista_contas_pagar")
        pagas = self.client.get(lista, {"status": "pago"})
        self.assertEqual(
            [conta.descricao for conta in pagas.context["contas"]],
            ["Energia paga"],
        )
        canceladas = self.client.get(lista, {"status": "cancelado"})
        self.assertEqual(
            [conta.descricao for conta in canceladas.context["contas"]],
            ["Taxa cancelada"],
        )

    def test_filtro_categoria(self):
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {"categoria": str(self.energia.pk)},
        )
        nomes = [conta.descricao for conta in response.context["contas"]]
        self.assertCountEqual(nomes, ["Energia paga", "Taxa cancelada"])

    def test_filtro_fornecedor_e_sem_fornecedor(self):
        _conta(self.energia, descricao="Sem posto", fornecedor=None)
        lista = reverse("financeiro:lista_contas_pagar")
        especifico = self.client.get(lista, {"fornecedor": str(self.forn_b.pk)})
        nomes = [conta.descricao for conta in especifico.context["contas"]]
        self.assertCountEqual(nomes, ["Energia paga", "Taxa cancelada"])
        sem = self.client.get(lista, {"fornecedor": "sem"})
        self.assertEqual(
            [conta.descricao for conta in sem.context["contas"]],
            ["Sem posto"],
        )
        legado = self.client.get(lista, {"sem_fornecedor": "1"})
        self.assertEqual(
            [conta.descricao for conta in legado.context["contas"]],
            ["Sem posto"],
        )

    def test_filtro_competencia_inicial_e_final(self):
        lista = reverse("financeiro:lista_contas_pagar")
        inicio = self.client.get(
            lista,
            {"competencia_inicio": self.hoje.replace(day=1).isoformat()},
        )
        self.assertNotIn(
            "Taxa cancelada",
            [conta.descricao for conta in inicio.context["contas"]],
        )
        fim_janeiro = self.hoje.replace(month=1, day=31)
        if self.hoje.month == 1:
            fim_janeiro = self.hoje.replace(year=self.hoje.year - 1, month=1, day=31)
        so_janeiro = self.client.get(
            lista,
            {"competencia_fim": fim_janeiro.isoformat()},
        )
        self.assertEqual(
            [conta.descricao for conta in so_janeiro.context["contas"]],
            ["Taxa cancelada"],
        )

    def test_filtro_vencimento_inicial_e_final(self):
        lista = reverse("financeiro:lista_contas_pagar")
        atrasadas = self.client.get(
            lista,
            {"vencimento_fim": (self.hoje - timedelta(days=1)).isoformat()},
        )
        self.assertEqual(
            [conta.descricao for conta in atrasadas.context["contas"]],
            ["Aluguel atrasado"],
        )
        futuras = self.client.get(
            lista,
            {"vencimento_inicio": (self.hoje + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(
            [conta.descricao for conta in futuras.context["contas"]],
            ["Aluguel loja"],
        )

    def test_filtro_forma_pagamento(self):
        _conta(
            self.energia,
            descricao="PIX oficina",
            forma_pagamento=ContaPagar.FORMA_PIX,
            data_vencimento=self.hoje + timedelta(days=8),
        )
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {"forma_pagamento": ContaPagar.FORMA_PIX},
        )
        self.assertEqual(
            [conta.descricao for conta in response.context["contas"]],
            ["PIX oficina"],
        )

    def test_filtro_veiculo_e_sem_veiculo(self):
        veiculo = criar_veiculo(placa="FLT1A23")
        _conta(
            self.energia,
            descricao="Combustível Fiorino",
            veiculo=veiculo,
            data_vencimento=self.hoje + timedelta(days=4),
        )
        lista = reverse("financeiro:lista_contas_pagar")
        com_veiculo = self.client.get(lista, {"veiculo": str(veiculo.pk)})
        self.assertEqual(
            [conta.descricao for conta in com_veiculo.context["contas"]],
            ["Combustível Fiorino"],
        )
        sem_veiculo = self.client.get(lista, {"veiculo": "sem", "q": "Energia paga"})
        self.assertEqual(
            [conta.descricao for conta in sem_veiculo.context["contas"]],
            ["Energia paga"],
        )

    def test_filtros_combinados(self):
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            {
                "status": "pendente",
                "categoria": str(self.aluguel.pk),
                "fornecedor": str(self.forn_a.pk),
                "q": "loja",
                "vencimento_inicio": self.hoje.isoformat(),
                "vencimento_fim": (self.hoje + timedelta(days=15)).isoformat(),
            },
        )
        self.assertEqual(
            [conta.descricao for conta in response.context["contas"]],
            ["Aluguel loja"],
        )
        self.assertEqual(response.context["totais"]["total_geral"], Decimal("1000.00"))
        self.assertEqual(response.context["filtros_ativos"], 6)

    def test_endpoint_parcial_autorizado_e_sem_permissao(self):
        lista = reverse("financeiro:lista_contas_pagar")
        ok = self.client.get(
            lista,
            {"q": "loja"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(ok.status_code, 200)
        self.assertContains(ok, "Aluguel loja")
        self.assertNotContains(ok, "Acompanhe vencimentos")
        self.assertNotContains(ok, "Aluguel atrasado")
        User = get_user_model()
        sem_perm = User.objects.create_user(username="fin-filtro-sem", password="x")
        self.client.force_login(sem_perm)
        negado = self.client.get(
            lista,
            {"q": "loja"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(negado.status_code, 403)

    def test_parcial_preserva_imutabilidade(self):
        User = get_user_model()
        editor = User.objects.create_user(username="fin-filtro-edit", password="x")
        conceder_permissoes(
            editor,
            "financeiro.view_contapagar",
            "financeiro.change_contapagar",
        )
        self.client.force_login(editor)
        response = self.client.get(
            reverse("financeiro:lista_contas_pagar"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertContains(response, "Editar")
        self.assertContains(response, "Conta paga — edição bloqueada")
        self.assertContains(response, "Conta cancelada — edição bloqueada")
        energia_paga = ContaPagar.objects.get(descricao="Energia paga")
        cancelada = ContaPagar.objects.get(descricao="Taxa cancelada")
        pendente = ContaPagar.objects.get(descricao="Aluguel loja")
        self.assertContains(
            response,
            reverse("financeiro:editar_conta_pagar", args=[pendente.pk]),
        )
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_pagar", args=[energia_paga.pk]),
        )
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_pagar", args=[cancelada.pk]),
        )


class ContaPagarListaVaziaTests(TestCase):
    def test_estado_sem_cadastro(self):
        User = get_user_model()
        user = User.objects.create_user(username="fin-vazio", password="x")
        conceder_permissoes(user, "financeiro.view_contapagar")
        self.client.force_login(user)
        response = self.client.get(reverse("financeiro:lista_contas_pagar"))
        self.assertContains(response, "Nenhuma conta cadastrada.")
        self.assertNotContains(
            response,
            "Não encontramos contas que correspondam aos filtros selecionados.",
        )


def _recorrente(categoria, **kwargs):
    dados = {
        "descricao": "Aluguel galpão",
        "categoria": categoria,
        "valor": Decimal("2000.00"),
        "dia_vencimento": 10,
        "data_inicio": date(2026, 1, 1),
        "ativa": True,
    }
    dados.update(kwargs)
    return ContaRecorrente.objects.create(**dados)


class ContaRecorrenteModelTests(TestCase):
    def setUp(self):
        self.categoria = CategoriaFinanceira.objects.get(slug="aluguel")

    def test_criacao_valida(self):
        item = _recorrente(self.categoria)
        self.assertTrue(item.ativa)
        self.assertFalse(item.valor_estimado)
        self.assertEqual(item.periodicidade, ContaRecorrente.PERIODICIDADE_MENSAL)

    def test_valor_invalido(self):
        zero = _recorrente(self.categoria, descricao="Zero", valor=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            zero.full_clean()
        negativo = _recorrente(self.categoria, descricao="Neg", valor=Decimal("-1.00"))
        with self.assertRaises(ValidationError):
            negativo.full_clean()

    def test_dia_limites(self):
        _recorrente(self.categoria, descricao="Dia 1", dia_vencimento=1).full_clean()
        _recorrente(self.categoria, descricao="Dia 28", dia_vencimento=28).full_clean()
        invalido = _recorrente(self.categoria, descricao="Dia 29", dia_vencimento=29)
        with self.assertRaises(ValidationError):
            invalido.full_clean()

    def test_data_fim_anterior_invalida(self):
        item = _recorrente(
            self.categoria,
            data_inicio=date(2026, 6, 1),
            data_fim=date(2026, 5, 1),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_categoria_exige_veiculo_invalida(self):
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        item = _recorrente(combustivel, descricao="Diesel mensal")
        with self.assertRaises(ValidationError) as contexto:
            item.full_clean()
        self.assertIn("categoria", contexto.exception.error_dict)
        self.assertIn(
            ContaRecorrente.MENSAGEM_CATEGORIA_EXIGE_VEICULO,
            contexto.exception.error_dict["categoria"][0],
        )


class ContaRecorrenteServicoTests(TestCase):
    def setUp(self):
        self.categoria = CategoriaFinanceira.objects.get(slug="energia-eletrica")
        self.fornecedor = Fornecedor.objects.create(nome="CPFL Rec")
        self.recorrente = _recorrente(
            self.categoria,
            descricao="Energia elétrica",
            fornecedor=self.fornecedor,
            valor=Decimal("600.00"),
            valor_estimado=True,
            dia_vencimento=15,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
        )

    def test_gera_conta_com_dados_copiados(self):
        resultado = gerar_conta_recorrente(self.recorrente, date(2026, 9, 20))
        self.assertTrue(resultado.criada)
        conta = resultado.conta
        self.assertEqual(conta.descricao, "Energia elétrica")
        self.assertEqual(conta.categoria, self.categoria)
        self.assertEqual(conta.fornecedor, self.fornecedor)
        self.assertEqual(conta.valor, Decimal("600.00"))
        self.assertEqual(conta.competencia, date(2026, 9, 1))
        self.assertEqual(conta.data_vencimento, date(2026, 9, 15))
        self.assertEqual(conta.status, ContaPagar.STATUS_PENDENTE)
        self.assertIsNone(conta.data_pagamento)
        self.assertEqual(conta.recorrente, self.recorrente)

    def test_duplicidade_mesma_competencia(self):
        gerar_conta_recorrente(self.recorrente, date(2026, 9, 1))
        segunda = gerar_conta_recorrente(self.recorrente, date(2026, 9, 1))
        self.assertTrue(segunda.ja_existia)
        self.assertEqual(
            ContaPagar.objects.filter(recorrente=self.recorrente, competencia=date(2026, 9, 1)).count(),
            1,
        )

    def test_conta_normal_sem_recorrencia(self):
        _conta(self.categoria, descricao="Avulsa", competencia=date(2026, 9, 1))
        gerar_conta_recorrente(self.recorrente, date(2026, 9, 1))
        self.assertEqual(ContaPagar.objects.filter(competencia=date(2026, 9, 1)).count(), 2)

    def test_vigencia_e_inativa(self):
        antes = gerar_conta_recorrente(self.recorrente, date(2025, 12, 1))
        self.assertTrue(antes.ignorada_vigencia)
        depois = gerar_conta_recorrente(self.recorrente, date(2027, 1, 1))
        self.assertTrue(depois.ignorada_vigencia)
        self.recorrente.ativa = False
        self.recorrente.save(update_fields=["ativa"])
        inativa = gerar_conta_recorrente(self.recorrente, date(2026, 9, 1))
        self.assertTrue(inativa.ignorada_inativa)
        self.assertEqual(ContaPagar.objects.filter(recorrente=self.recorrente).count(), 0)

    def test_alteracao_nao_muda_conta_antiga(self):
        julho = gerar_conta_recorrente(self.recorrente, date(2026, 7, 1)).conta
        self.recorrente.valor = Decimal("800.00")
        self.recorrente.save(update_fields=["valor"])
        setembro = gerar_conta_recorrente(self.recorrente, date(2026, 9, 1)).conta
        julho.refresh_from_db()
        self.assertEqual(julho.valor, Decimal("600.00"))
        self.assertEqual(setembro.valor, Decimal("800.00"))

    def test_set_null_ao_remover_recorrente(self):
        conta = gerar_conta_recorrente(self.recorrente, date(2026, 8, 1)).conta
        pk = conta.pk
        self.recorrente.delete()
        conta = ContaPagar.objects.get(pk=pk)
        self.assertIsNone(conta.recorrente)

    def test_gerar_competencia_resume_e_idempotencia(self):
        outra = _recorrente(
            self.categoria,
            descricao="Internet",
            valor=Decimal("120.00"),
            dia_vencimento=5,
            data_inicio=date(2026, 1, 1),
        )
        inativa = _recorrente(
            self.categoria,
            descricao="Inativa",
            valor=Decimal("10.00"),
            dia_vencimento=2,
            data_inicio=date(2026, 1, 1),
            ativa=False,
        )
        primeira = gerar_competencia(9, 2026)
        self.assertEqual(primeira.criadas, 2)
        self.assertEqual(primeira.existentes, 0)
        self.assertEqual(primeira.inativas, 1)
        segunda = gerar_competencia(9, 2026)
        self.assertEqual(segunda.criadas, 0)
        self.assertEqual(segunda.existentes, 2)
        self.assertEqual(inativa.contas_geradas.count(), 0)
        self.assertEqual(segunda.erros, [])

    def test_form_bloqueia_categoria_exige_veiculo(self):
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        form = ContaRecorrenteForm(
            data={
                "descricao": "Combustível frota",
                "categoria": combustivel.pk,
                "valor": "500.00",
                "periodicidade": ContaRecorrente.PERIODICIDADE_MENSAL,
                "dia_vencimento": "10",
                "data_inicio": "2026-01-01",
                "ativa": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("categoria", form.errors)
        self.assertIn(
            ContaRecorrente.MENSAGEM_CATEGORIA_EXIGE_VEICULO,
            form.errors["categoria"][0],
        )

    def test_gerar_competencia_isola_recorrencia_invalida(self):
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        valida_a = _recorrente(
            self.categoria,
            descricao="Recorrencia A",
            valor=Decimal("100.00"),
            dia_vencimento=5,
            data_inicio=date(2026, 1, 1),
        )
        invalida = _recorrente(
            combustivel,
            descricao="Recorrencia B",
            valor=Decimal("200.00"),
            dia_vencimento=6,
            data_inicio=date(2026, 1, 1),
        )
        valida_c = _recorrente(
            self.categoria,
            descricao="Recorrencia C",
            valor=Decimal("300.00"),
            dia_vencimento=7,
            data_inicio=date(2026, 1, 1),
        )
        primeira = gerar_competencia(9, 2026)
        self.assertEqual(primeira.criadas, 3)
        self.assertEqual(len(primeira.erros), 1)
        self.assertEqual(primeira.erros[0].descricao, "Recorrencia B")
        self.assertEqual(
            primeira.erros[0].motivo,
            ContaRecorrente.MENSAGEM_CATEGORIA_EXIGE_VEICULO,
        )
        self.assertTrue(
            ContaPagar.objects.filter(recorrente=valida_a, competencia=date(2026, 9, 1)).exists()
        )
        self.assertTrue(
            ContaPagar.objects.filter(recorrente=valida_c, competencia=date(2026, 9, 1)).exists()
        )
        self.assertFalse(ContaPagar.objects.filter(recorrente=invalida).exists())

        segunda = gerar_competencia(9, 2026)
        self.assertEqual(segunda.criadas, 0)
        self.assertEqual(segunda.existentes, 3)
        self.assertEqual(len(segunda.erros), 1)
        self.assertEqual(
            ContaPagar.objects.filter(competencia=date(2026, 9, 1)).count(),
            3,
        )


class ContaRecorrenteUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.categoria = CategoriaFinanceira.objects.get(slug="aluguel")
        self.com_perm = User.objects.create_user(
            username="fin-rec-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "financeiro.view_contarecorrente",
            "financeiro.add_contarecorrente",
            "financeiro.change_contarecorrente",
            "financeiro.add_contapagar",
        )
        self.sem_perm = User.objects.create_user(
            username="fin-rec-sem",
            password="teste-123",
        )
        self.sem_add_conta = User.objects.create_user(
            username="fin-rec-sem-add",
            password="teste-123",
        )
        conceder_permissoes(
            self.sem_add_conta,
            "financeiro.view_contarecorrente",
            "financeiro.change_contarecorrente",
        )
        self.item = _recorrente(self.categoria)

    def test_lista_permissoes(self):
        url = reverse("financeiro:lista_contas_recorrentes")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.sem_perm)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.com_perm)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aluguel galpão")
        self.assertContains(response, "Contas recorrentes")

    def test_cadastro_edicao_e_toggle(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_recorrente"),
            {
                "descricao": "Internet escritório",
                "categoria": self.categoria.pk,
                "valor": "199.90",
                "periodicidade": ContaRecorrente.PERIODICIDADE_MENSAL,
                "dia_vencimento": "8",
                "data_inicio": "2026-01-01",
                "ativa": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        criada = ContaRecorrente.objects.get(descricao="Internet escritório")
        response = self.client.post(
            reverse("financeiro:editar_conta_recorrente", args=[criada.pk]),
            {
                "descricao": "Internet escritório",
                "categoria": self.categoria.pk,
                "valor": "210.00",
                "periodicidade": ContaRecorrente.PERIODICIDADE_MENSAL,
                "dia_vencimento": "8",
                "data_inicio": "2026-01-01",
                "ativa": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        criada.refresh_from_db()
        self.assertEqual(criada.valor, Decimal("210.00"))
        self.client.post(
            reverse("financeiro:alternar_ativo_conta_recorrente", args=[self.item.pk])
        )
        self.item.refresh_from_db()
        self.assertFalse(self.item.ativa)

    def test_post_bloqueia_categoria_exige_veiculo(self):
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_recorrente"),
            {
                "descricao": "IPVA parcelado",
                "categoria": combustivel.pk,
                "valor": "150.00",
                "periodicidade": ContaRecorrente.PERIODICIDADE_MENSAL,
                "dia_vencimento": "10",
                "data_inicio": "2026-01-01",
                "ativa": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ContaRecorrente.objects.filter(descricao="IPVA parcelado").exists()
        )
        self.assertContains(
            response,
            "Categorias que exigem veículo não podem ser usadas",
        )

    def test_gerar_exige_add_contapagar(self):
        url = reverse("financeiro:gerar_contas_recorrentes")
        self.client.force_login(self.sem_add_conta)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.com_perm)
        response = self.client.post(url, {"mes": "9", "ano": "2026"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "contas criadas")
        self.assertEqual(ContaPagar.objects.filter(recorrente=self.item).count(), 1)
        self.assertEqual(
            ContaPagar.objects.get(recorrente=self.item).criado_por,
            self.com_perm,
        )

    def test_filtro_ativa(self):
        self.item.ativa = False
        self.item.save(update_fields=["ativa"])
        self.client.force_login(self.com_perm)
        response = self.client.get(
            reverse("financeiro:lista_contas_recorrentes"),
            {"ativa": "0"},
        )
        nomes = [item.descricao for item in response.context["recorrentes"]]
        self.assertEqual(nomes, ["Aluguel galpão"])


class GerarContasRecorrentesCommandTests(TestCase):
    def setUp(self):
        self.categoria = CategoriaFinanceira.objects.get(slug="contabilidade")
        _recorrente(
            self.categoria,
            descricao="Contador",
            valor=Decimal("400.00"),
            dia_vencimento=12,
            data_inicio=date(2026, 1, 1),
        )

    def test_comando_com_mes_ano(self):
        saida = StringIO()
        call_command("gerar_contas_recorrentes", mes=9, ano=2026, stdout=saida)
        texto = saida.getvalue()
        self.assertIn("1 criadas", texto)
        self.assertEqual(ContaPagar.objects.count(), 1)
        saida = StringIO()
        call_command("gerar_contas_recorrentes", mes=9, ano=2026, stdout=saida)
        self.assertIn("0 criadas", saida.getvalue())
        self.assertIn("1 já existentes", saida.getvalue())

    def test_comando_sem_parametros_usa_mes_atual(self):
        hoje = dia_local_atual()
        call_command("gerar_contas_recorrentes")
        self.assertTrue(
            ContaPagar.objects.filter(
                competencia=date(hoje.year, hoje.month, 1)
            ).exists()
        )

