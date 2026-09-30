from datetime import timedelta
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from clientes.models import Cliente
from core.periodo import dia_local_atual
from financeiro.admin import ContaReceberAdmin
from financeiro.forms import ContaReceberForm
from financeiro.models import CategoriaFinanceira, ContaPagar, ContaReceber
from produtos.models import Produto
from vendas.models import ItemVenda, Venda


def _categoria_receita(**kwargs):
    dados = {
        "nome": "Vendas",
        "slug": "vendas-receita",
        "tipo": CategoriaFinanceira.TIPO_RECEITA,
        "ordem": 10,
    }
    dados.update(kwargs)
    categoria, _criada = CategoriaFinanceira.objects.get_or_create(
        slug=dados["slug"],
        defaults=dados,
    )
    return categoria


def _conta_receber(cliente, categoria, **kwargs):
    hoje = dia_local_atual()
    dados = {
        "descricao": "Receita teste",
        "cliente": cliente,
        "categoria": categoria,
        "competencia": hoje.replace(day=1),
        "valor": Decimal("100.00"),
        "data_vencimento": hoje,
        "status": ContaReceber.STATUS_PENDENTE,
    }
    dados.update(kwargs)
    return ContaReceber.objects.create(**dados)


class ContaReceberModelTests(TestCase):
    def setUp(self):
        self.hoje = dia_local_atual()
        self.cliente = Cliente.objects.create(nome="Padaria Central")
        self.categoria = _categoria_receita()
        self.despesa = CategoriaFinanceira.objects.get(slug="aluguel")

    def test_criacao_valida(self):
        conta = _conta_receber(self.cliente, self.categoria)
        self.assertEqual(conta.status, ContaReceber.STATUS_PENDENTE)
        self.assertFalse(conta.vencida)

    def test_valor_zero_e_negativo_invalidos(self):
        zero = _conta_receber(self.cliente, self.categoria, valor=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            zero.full_clean()
        negativo = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Negativa",
            valor=Decimal("-10.00"),
        )
        with self.assertRaises(ValidationError):
            negativo.full_clean()

    def test_categoria_despesa_rejeitada(self):
        conta = _conta_receber(self.cliente, self.despesa)
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("categoria", contexto.exception.error_dict)

    def test_categoria_receita_aceita(self):
        conta = _conta_receber(self.cliente, self.categoria)
        conta.full_clean()

    def test_recebida_exige_data(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            status=ContaReceber.STATUS_RECEBIDA,
        )
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def test_pendente_nao_aceita_data_recebimento(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            data_recebimento=self.hoje,
        )
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def test_cancelada_nao_aceita_data_recebimento(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            status=ContaReceber.STATUS_CANCELADA,
            data_recebimento=self.hoje,
        )
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def test_recebimento_antes_da_emissao_invalido(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            data_emissao=self.hoje,
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def test_vencida_somente_pendente_atrasada(self):
        futura = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Futura",
            data_vencimento=self.hoje + timedelta(days=5),
        )
        atrasada = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Atrasada",
            data_vencimento=self.hoje - timedelta(days=1),
        )
        recebida = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Recebida atrasada",
            data_vencimento=self.hoje - timedelta(days=1),
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje,
        )
        cancelada = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Cancelada atrasada",
            data_vencimento=self.hoje - timedelta(days=1),
            status=ContaReceber.STATUS_CANCELADA,
        )
        self.assertFalse(futura.vencida)
        self.assertTrue(atrasada.vencida)
        self.assertFalse(recebida.vencida)
        self.assertFalse(cancelada.vencida)

    def test_recebida_nao_pode_reabrir_pelo_save(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje,
            valor=Decimal("80.00"),
        )
        conta.status = ContaReceber.STATUS_PENDENTE
        conta.data_recebimento = None
        with self.assertRaises(ValidationError):
            conta.save()
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.STATUS_RECEBIDA)


class ContaReceberVendaTests(TestCase):
    def setUp(self):
        self.hoje = dia_local_atual()
        self.cliente = Cliente.objects.create(nome="Mercado Sul")
        self.outro = Cliente.objects.create(nome="Outro Cliente")
        self.categoria = _categoria_receita()
        self.produto = Produto.objects.create(
            nome="Gelo 20kg receber",
            peso_kg=Decimal("20.11"),
            preco_venda=Decimal("50.00"),
        )
        self.venda = Venda.objects.create(cliente=self.cliente)
        ItemVenda.objects.create(
            venda=self.venda,
            produto=self.produto,
            quantidade=Decimal("2"),
        )

    def test_vinculo_valido(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            venda=self.venda,
            valor=Decimal("100.00"),
            descricao="Venda #vinculo",
        )
        conta.full_clean()
        self.assertEqual(conta.venda_id, self.venda.pk)
        self.assertEqual(self.venda.conta_receber.pk, conta.pk)

    def test_cliente_diferente_da_venda_rejeitado(self):
        conta = _conta_receber(
            self.outro,
            self.categoria,
            venda=self.venda,
            valor=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("venda", contexto.exception.error_dict)

    def test_segunda_conta_mesma_venda_rejeitada(self):
        _conta_receber(
            self.cliente,
            self.categoria,
            venda=self.venda,
            valor=Decimal("100.00"),
            descricao="Primeira",
        )
        with self.assertRaises(IntegrityError):
            _conta_receber(
                self.cliente,
                self.categoria,
                venda=self.venda,
                valor=Decimal("100.00"),
                descricao="Segunda",
            )

    def test_valor_diferente_do_total_rejeitado(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            venda=self.venda,
            valor=Decimal("80.00"),
        )
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("valor", contexto.exception.error_dict)


class ContaReceberFormTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente ativo")
        self.inativo = Cliente.objects.create(nome="Cliente inativo", ativo=False)
        self.categoria = _categoria_receita()
        self.despesa = CategoriaFinanceira.objects.get(slug="aluguel")

    def test_formulario_lista_somente_receita_e_cliente_ativo(self):
        form = ContaReceberForm()
        self.assertIn(self.categoria, form.fields["categoria"].queryset)
        self.assertNotIn(self.despesa, form.fields["categoria"].queryset)
        self.assertIn(self.cliente, form.fields["cliente"].queryset)
        self.assertNotIn(self.inativo, form.fields["cliente"].queryset)

    def test_edicao_preserva_cliente_inativo(self):
        conta = _conta_receber(self.inativo, self.categoria)
        form = ContaReceberForm(instance=conta)
        self.assertIn(self.inativo, form.fields["cliente"].queryset)


class ContaReceberViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.hoje = dia_local_atual()
        self.cliente = Cliente.objects.create(nome="Cliente UI")
        self.categoria = _categoria_receita()
        self.com_perm = User.objects.create_user(
            username="fin-cr-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "financeiro.view_contareceber",
            "financeiro.add_contareceber",
            "financeiro.change_contareceber",
        )
        self.sem_perm = User.objects.create_user(
            username="fin-cr-sem",
            password="teste-123",
        )
        self.conta = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Serviço mensal",
            valor=Decimal("250.00"),
            data_vencimento=self.hoje - timedelta(days=2),
        )

    def _payload(self, **overrides):
        dados = {
            "descricao": "Nova receita",
            "cliente": self.cliente.pk,
            "categoria": self.categoria.pk,
            "competencia": self.hoje.replace(day=1).isoformat(),
            "valor": "80.50",
            "data_vencimento": self.hoje.isoformat(),
            "status": ContaReceber.STATUS_PENDENTE,
            "observacoes": "",
            "forma_recebimento": "",
        }
        dados.update(overrides)
        return dados

    def test_lista_anonimo_redireciona(self):
        response = self.client.get(reverse("financeiro:lista_contas_receber"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_lista_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("financeiro:lista_contas_receber"))
        self.assertEqual(response.status_code, 403)

    def test_lista_com_permissao(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:lista_contas_receber"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Serviço mensal")
        self.assertContains(response, "Vencida")
        self.assertContains(
            response,
            reverse("financeiro:editar_conta_receber", args=[self.conta.pk]),
        )

    def test_cadastro_preenche_criado_por(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_receber"),
            self._payload(),
        )
        self.assertEqual(response.status_code, 302)
        criada = ContaReceber.objects.get(descricao="Nova receita")
        self.assertEqual(criada.criado_por, self.com_perm)
        self.assertEqual(criada.valor, Decimal("80.50"))

    def test_edicao_pendente(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:editar_conta_receber", args=[self.conta.pk]),
            self._payload(descricao="Serviço atualizado", valor="250.00"),
        )
        self.assertEqual(response.status_code, 302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.descricao, "Serviço atualizado")

    def test_marcar_recebida_somente_post(self):
        self.client.force_login(self.com_perm)
        url = reverse("financeiro:marcar_conta_recebida", args=[self.conta.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, ContaReceber.STATUS_RECEBIDA)
        self.assertEqual(self.conta.data_recebimento, self.hoje)

    def test_cancelar_somente_post(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Para cancelar",
        )
        self.client.force_login(self.com_perm)
        url = reverse("financeiro:cancelar_conta_receber", args=[conta.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.STATUS_CANCELADA)

    def test_acoes_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        self.assertEqual(
            self.client.post(
                reverse("financeiro:marcar_conta_recebida", args=[self.conta.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("financeiro:cancelar_conta_receber", args=[self.conta.pk])
            ).status_code,
            403,
        )

    def test_recebida_nao_pode_editar(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Já recebida",
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje,
            valor=Decimal("70.00"),
        )
        self.client.force_login(self.com_perm)
        url = reverse("financeiro:editar_conta_receber", args=[conta.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(
            url,
            self._payload(
                descricao="Alterada",
                valor="1.00",
                status=ContaReceber.STATUS_PENDENTE,
            ),
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.descricao, "Já recebida")
        self.assertEqual(conta.valor, Decimal("70.00"))
        self.assertEqual(conta.status, ContaReceber.STATUS_RECEBIDA)

    def test_cancelada_nao_pode_editar(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Já cancelada",
            status=ContaReceber.STATUS_CANCELADA,
            valor=Decimal("40.00"),
        )
        self.client.force_login(self.com_perm)
        url = reverse("financeiro:editar_conta_receber", args=[conta.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(
            url,
            self._payload(valor="2.00", status=ContaReceber.STATUS_PENDENTE),
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.STATUS_CANCELADA)
        self.assertEqual(conta.valor, Decimal("40.00"))

    def test_lista_esconde_editar_fechadas(self):
        recebida = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Recebida lista",
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje,
        )
        cancelada = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Cancelada lista",
            status=ContaReceber.STATUS_CANCELADA,
        )
        self.client.force_login(self.com_perm)
        response = self.client.get(reverse("financeiro:lista_contas_receber"))
        self.assertContains(response, "Conta recebida — edição bloqueada")
        self.assertContains(response, "Conta cancelada — edição bloqueada")
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_receber", args=[recebida.pk]),
        )
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_receber", args=[cancelada.pk]),
        )

    def test_recebida_nao_pode_cancelar(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje,
        )
        self.client.force_login(self.com_perm)
        self.client.post(
            reverse("financeiro:cancelar_conta_receber", args=[conta.pk])
        )
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.STATUS_RECEBIDA)

    def test_cancelada_nao_pode_marcar_recebida(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            status=ContaReceber.STATUS_CANCELADA,
        )
        self.client.force_login(self.com_perm)
        self.client.post(
            reverse("financeiro:marcar_conta_recebida", args=[conta.pk])
        )
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.STATUS_CANCELADA)


class ContaReceberAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.hoje = dia_local_atual()
        self.cliente = Cliente.objects.create(nome="Admin cliente")
        self.categoria = _categoria_receita()
        self.admin_user = User.objects.create_superuser(
            username="fin-admin-cr",
            password="teste-123",
        )
        self.factory = RequestFactory()
        self.model_admin = ContaReceberAdmin(ContaReceber, AdminSite())

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.admin_user
        return request

    def test_pendente_editavel_no_admin(self):
        conta = _conta_receber(self.cliente, self.categoria, descricao="Admin pendente")
        self.assertTrue(self.model_admin.has_change_permission(self._request(), conta))
        self.client.force_login(self.admin_user)
        url = reverse("admin:financeiro_contareceber_change", args=[conta.pk])
        response = self.client.post(
            url,
            {
                "descricao": "Admin pendente editada",
                "cliente": self.cliente.pk,
                "categoria": self.categoria.pk,
                "competencia": conta.competencia.isoformat(),
                "valor": "111.00",
                "data_vencimento": conta.data_vencimento.isoformat(),
                "status": ContaReceber.STATUS_PENDENTE,
                "observacoes": "",
                "forma_recebimento": "",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.descricao, "Admin pendente editada")

    def test_recebida_protegida_no_admin(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Admin recebida",
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje,
            valor=Decimal("90.00"),
        )
        self.assertFalse(self.model_admin.has_change_permission(self._request(), conta))
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("admin:financeiro_contareceber_change", args=[conta.pk]),
            {
                "descricao": "Tentativa",
                "cliente": self.cliente.pk,
                "categoria": self.categoria.pk,
                "competencia": conta.competencia.isoformat(),
                "valor": "1.00",
                "data_vencimento": conta.data_vencimento.isoformat(),
                "status": ContaReceber.STATUS_PENDENTE,
                "observacoes": "",
                "forma_recebimento": "",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.valor, Decimal("90.00"))
        self.assertEqual(conta.status, ContaReceber.STATUS_RECEBIDA)

    def test_cancelada_protegida_no_admin(self):
        conta = _conta_receber(
            self.cliente,
            self.categoria,
            descricao="Admin cancelada",
            status=ContaReceber.STATUS_CANCELADA,
            valor=Decimal("33.00"),
        )
        self.assertFalse(self.model_admin.has_change_permission(self._request(), conta))
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("admin:financeiro_contareceber_change", args=[conta.pk]),
            {
                "descricao": "Tentativa",
                "cliente": self.cliente.pk,
                "categoria": self.categoria.pk,
                "competencia": conta.competencia.isoformat(),
                "valor": "2.00",
                "data_vencimento": conta.data_vencimento.isoformat(),
                "status": ContaReceber.STATUS_PENDENTE,
                "observacoes": "",
                "forma_recebimento": "",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 403)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.STATUS_CANCELADA)
        self.assertEqual(conta.valor, Decimal("33.00"))


class ContaReceberRegressaoPagarTests(TestCase):
    def test_contapagar_continua_existindo(self):
        self.assertTrue(ContaPagar._meta.get_field("status"))


class ContaReceberFiltroTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.hoje = dia_local_atual()
        self.cliente_a = Cliente.objects.create(nome="Padaria Aurora")
        self.cliente_b = Cliente.objects.create(nome="Mercado Beta")
        self.vendas = _categoria_receita()
        self.servicos = _categoria_receita(
            nome="Serviços",
            slug="servicos-filtro-receita",
            ordem=20,
        )
        self.despesa = CategoriaFinanceira.objects.get(slug="aluguel")
        self.user = User.objects.create_user(username="fin-cr-filtro", password="x")
        conceder_permissoes(
            self.user,
            "financeiro.view_contareceber",
            "financeiro.change_contareceber",
        )
        self.somente_ver = User.objects.create_user(
            username="fin-cr-ver",
            password="x",
        )
        conceder_permissoes(self.somente_ver, "financeiro.view_contareceber")
        self.sem_perm = User.objects.create_user(username="fin-cr-filtro-sem", password="x")
        self.client.force_login(self.user)
        self.lista = reverse("financeiro:lista_contas_receber")

        self.pendente = _conta_receber(
            self.cliente_a,
            self.vendas,
            descricao="Mensalidade loja",
            valor=Decimal("1000.00"),
            competencia=self.hoje.replace(day=1),
            data_vencimento=self.hoje + timedelta(days=10),
            observacoes="CONTRATO ANUAL",
        )
        self.vencida = _conta_receber(
            self.cliente_a,
            self.vendas,
            descricao="Aluguel atrasado rec",
            valor=Decimal("200.00"),
            competencia=self.hoje.replace(day=1),
            data_vencimento=self.hoje - timedelta(days=3),
        )
        self.recebida = _conta_receber(
            self.cliente_b,
            self.servicos,
            descricao="Serviço recebido",
            valor=Decimal("300.00"),
            competencia=self.hoje.replace(day=1),
            status=ContaReceber.STATUS_RECEBIDA,
            data_recebimento=self.hoje,
            forma_recebimento=ContaReceber.FORMA_PIX,
        )
        competencia_jan = (
            self.hoje.replace(month=1, day=1)
            if self.hoje.month != 1
            else self.hoje.replace(year=self.hoje.year - 1, month=1, day=1)
        )
        self.cancelada = _conta_receber(
            self.cliente_b,
            self.servicos,
            descricao="Taxa cancelada rec",
            valor=Decimal("50.00"),
            competencia=competencia_jan,
            status=ContaReceber.STATUS_CANCELADA,
        )
        self.produto = Produto.objects.create(
            nome="Gelo filtro receber",
            peso_kg=Decimal("20.00"),
            preco_venda=Decimal("40.00"),
        )
        self.venda = Venda.objects.create(cliente=self.cliente_a)
        ItemVenda.objects.create(
            venda=self.venda,
            produto=self.produto,
            quantidade=Decimal("2"),
        )
        self.vinculada = _conta_receber(
            self.cliente_a,
            self.vendas,
            descricao="Venda vinculada",
            valor=Decimal("80.00"),
            competencia=self.hoje.replace(day=1),
            data_vencimento=self.hoje + timedelta(days=5),
            venda=self.venda,
        )

    def _nomes(self, response):
        return [conta.descricao for conta in response.context["contas"]]

    def test_busca_por_descricao(self):
        response = self.client.get(self.lista, {"q": "loja"})
        self.assertEqual(self._nomes(response), ["Mensalidade loja"])

    def test_busca_por_cliente(self):
        response = self.client.get(self.lista, {"q": "aurora"})
        self.assertCountEqual(
            self._nomes(response),
            ["Mensalidade loja", "Aluguel atrasado rec", "Venda vinculada"],
        )

    def test_busca_por_observacao(self):
        response = self.client.get(self.lista, {"q": "CONTRATO ANUAL"})
        self.assertEqual(self._nomes(response), ["Mensalidade loja"])

    def test_busca_sem_resultados(self):
        response = self.client.get(self.lista, {"q": "xyz-inexistente"})
        self.assertEqual(list(response.context["contas"]), [])
        self.assertContains(response, "Nenhuma conta a receber encontrada.")
        self.assertContains(
            response,
            "Não encontramos contas a receber com os filtros selecionados.",
        )

    def test_filtro_status_pendente_nao_inclui_vencida(self):
        response = self.client.get(self.lista, {"status": "pendente"})
        nomes = self._nomes(response)
        self.assertIn("Mensalidade loja", nomes)
        self.assertIn("Venda vinculada", nomes)
        self.assertNotIn("Aluguel atrasado rec", nomes)
        self.assertNotIn("Serviço recebido", nomes)

    def test_filtro_status_recebida(self):
        response = self.client.get(self.lista, {"status": "recebida"})
        self.assertEqual(self._nomes(response), ["Serviço recebido"])

    def test_filtro_status_cancelada(self):
        response = self.client.get(self.lista, {"status": "cancelada"})
        self.assertEqual(self._nomes(response), ["Taxa cancelada rec"])

    def test_filtro_status_vencida(self):
        response = self.client.get(self.lista, {"status": "vencida"})
        self.assertEqual(self._nomes(response), ["Aluguel atrasado rec"])
        self.assertNotIn("Serviço recebido", self._nomes(response))
        self.assertNotIn("Taxa cancelada rec", self._nomes(response))

    def test_filtro_categoria_receita(self):
        response = self.client.get(self.lista, {"categoria": str(self.servicos.pk)})
        self.assertCountEqual(
            self._nomes(response),
            ["Serviço recebido", "Taxa cancelada rec"],
        )
        tipos = {cat.tipo for cat in response.context["categorias_filtro"]}
        self.assertEqual(tipos, {CategoriaFinanceira.TIPO_RECEITA})
        self.assertNotIn(self.despesa, list(response.context["categorias_filtro"]))

    def test_filtro_cliente(self):
        response = self.client.get(self.lista, {"cliente": str(self.cliente_b.pk)})
        self.assertCountEqual(
            self._nomes(response),
            ["Serviço recebido", "Taxa cancelada rec"],
        )

    def test_filtro_competencia_inicio_fim_e_intervalo(self):
        inicio = self.client.get(
            self.lista,
            {"competencia_inicio": self.hoje.replace(day=1).isoformat()},
        )
        self.assertNotIn("Taxa cancelada rec", self._nomes(inicio))
        fim_janeiro = self.hoje.replace(month=1, day=31)
        if self.hoje.month == 1:
            fim_janeiro = self.hoje.replace(year=self.hoje.year - 1, month=1, day=31)
        so_janeiro = self.client.get(
            self.lista,
            {"competencia_fim": fim_janeiro.isoformat()},
        )
        self.assertEqual(self._nomes(so_janeiro), ["Taxa cancelada rec"])
        intervalo = self.client.get(
            self.lista,
            {
                "competencia_inicio": self.hoje.replace(day=1).isoformat(),
                "competencia_fim": self.hoje.isoformat(),
            },
        )
        self.assertNotIn("Taxa cancelada rec", self._nomes(intervalo))
        self.assertIn("Mensalidade loja", self._nomes(intervalo))

    def test_filtro_vencimento_inicio_fim_e_intervalo(self):
        atrasadas = self.client.get(
            self.lista,
            {"vencimento_fim": (self.hoje - timedelta(days=1)).isoformat()},
        )
        self.assertEqual(self._nomes(atrasadas), ["Aluguel atrasado rec"])
        futuras = self.client.get(
            self.lista,
            {"vencimento_inicio": (self.hoje + timedelta(days=1)).isoformat()},
        )
        self.assertCountEqual(
            self._nomes(futuras),
            ["Mensalidade loja", "Venda vinculada"],
        )
        intervalo = self.client.get(
            self.lista,
            {
                "vencimento_inicio": (self.hoje + timedelta(days=4)).isoformat(),
                "vencimento_fim": (self.hoje + timedelta(days=12)).isoformat(),
            },
        )
        self.assertCountEqual(
            self._nomes(intervalo),
            ["Mensalidade loja", "Venda vinculada"],
        )

    def test_filtro_forma_recebimento(self):
        response = self.client.get(
            self.lista,
            {"forma_recebimento": ContaReceber.FORMA_PIX},
        )
        self.assertEqual(self._nomes(response), ["Serviço recebido"])

    def test_filtro_venda_com_e_sem(self):
        com_venda = self.client.get(self.lista, {"venda": "com"})
        self.assertEqual(self._nomes(com_venda), ["Venda vinculada"])
        sem_venda = self.client.get(self.lista, {"venda": "sem", "q": "Mensalidade"})
        self.assertEqual(self._nomes(sem_venda), ["Mensalidade loja"])

    def test_filtros_combinados(self):
        response = self.client.get(
            self.lista,
            {
                "cliente": str(self.cliente_a.pk),
                "status": "pendente",
                "competencia_inicio": self.hoje.replace(day=1).isoformat(),
                "competencia_fim": self.hoje.isoformat(),
                "vencimento_inicio": self.hoje.isoformat(),
                "vencimento_fim": (self.hoje + timedelta(days=15)).isoformat(),
            },
        )
        self.assertCountEqual(
            self._nomes(response),
            ["Mensalidade loja", "Venda vinculada"],
        )
        self.assertEqual(response.context["totais"]["total_geral"], Decimal("1080.00"))
        self.assertEqual(response.context["filtros_ativos"], 6)

    def test_totais_respeitam_queryset_filtrado(self):
        response = self.client.get(self.lista)
        totais = response.context["totais"]
        self.assertEqual(totais["total_geral"], Decimal("1630.00"))
        self.assertEqual(totais["total_pendente"], Decimal("1280.00"))
        self.assertEqual(totais["total_a_receber"], Decimal("1080.00"))
        self.assertEqual(totais["total_vencido"], Decimal("200.00"))
        self.assertEqual(totais["total_recebido"], Decimal("300.00"))
        self.assertEqual(totais["total_cancelado"], Decimal("50.00"))
        self.assertContains(response, "A receber")
        self.assertContains(response, "Em atraso")

    def test_totais_consideram_todas_as_paginas(self):
        for indice in range(26):
            _conta_receber(
                self.cliente_b,
                self.servicos,
                descricao=f"Lote rec {indice:02d}",
                valor=Decimal("10.00"),
                data_vencimento=self.hoje + timedelta(days=20),
            )
        response = self.client.get(self.lista, {"q": "Lote rec", "page": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["contas"]), 1)
        self.assertEqual(response.context["totais"]["total_geral"], Decimal("260.00"))
        self.assertTrue(response.context["page_obj"].has_previous())
        self.assertIn("q=Lote+rec", response.context["filtro_querystring"])
        self.assertNotIn("page=", response.context["filtro_querystring"])
        self.assertContains(response, "page=1")

    def test_pagina_completa_e_fragmento_ajax(self):
        completa = self.client.get(self.lista, {"q": "loja"})
        self.assertContains(completa, "Receitas pendentes")
        self.assertContains(completa, "Mensalidade loja")
        parcial = self.client.get(
            self.lista,
            {"q": "loja"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(parcial.status_code, 200)
        self.assertContains(parcial, "Mensalidade loja")
        self.assertNotContains(parcial, "Receitas pendentes")
        self.assertNotContains(parcial, "Aluguel atrasado rec")

    def test_parametros_invalidos_nao_geram_500(self):
        response = self.client.get(
            self.lista,
            {
                "cliente": "abc",
                "categoria": "xyz",
                "venda": "nope",
                "competencia_inicio": "12-13-2020",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_ajax_preserva_imutabilidade(self):
        response = self.client.get(
            self.lista,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertContains(
            response,
            reverse("financeiro:editar_conta_receber", args=[self.pendente.pk]),
        )
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_receber", args=[self.recebida.pk]),
        )
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_receber", args=[self.cancelada.pk]),
        )
        self.assertContains(response, "Conta recebida — edição bloqueada")
        self.assertContains(response, "Conta cancelada — edição bloqueada")

    def test_lista_sem_permissao_403_inclusive_ajax(self):
        self.client.force_login(self.sem_perm)
        self.assertEqual(self.client.get(self.lista).status_code, 403)
        self.assertEqual(
            self.client.get(
                self.lista,
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            ).status_code,
            403,
        )

    def test_acoes_exigem_change(self):
        self.client.force_login(self.somente_ver)
        response = self.client.get(self.lista)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse("financeiro:editar_conta_receber", args=[self.pendente.pk]),
        )
        self.assertEqual(
            self.client.post(
                reverse("financeiro:marcar_conta_recebida", args=[self.pendente.pk])
            ).status_code,
            403,
        )

    def test_listagem_nao_gera_n_plus_one_nas_relacoes(self):
        response = self.client.get(self.lista)
        contas = list(response.context["contas"])
        with CaptureQueriesContext(connection) as ctx:
            for conta in contas:
                _ = conta.cliente.nome
                _ = conta.categoria.nome
                _ = conta.venda_id
        self.assertEqual(len(ctx.captured_queries), 0)
        select_related = response.context["contas"].query.select_related
        self.assertIn("cliente", select_related)
        self.assertIn("categoria", select_related)
        self.assertIn("venda", select_related)
