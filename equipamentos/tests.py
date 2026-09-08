from datetime import date

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from pathlib import Path

from django.conf import settings

from accounts.test_utils import conceder_permissoes
from clientes.models import Cliente
from equipamentos.admin import ContratoComodatoAdmin
from equipamentos.forms import ContratoComodatoForm, DocumentoEquipamentoForm
from equipamentos.models import ContratoComodato, DocumentoEquipamento, Equipamento
from equipamentos.validators import MENSAGEM_CONTEUDO_INVALIDO, MENSAGEM_TIPO_NAO_PERMITIDO

PDF_MINIMO = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
PNG_MINIMO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"
)
HTML_XSS = b"<html><script>alert(1)</script></html>"


class DocumentoUploadValidacaoTests(TestCase):

    def setUp(self):
        self.equipamento = Equipamento.objects.create(
            nome="Equipamento documento",
            tipo="maquina_gelo",
        )

    def _formulario(self, nome_arquivo, conteudo, content_type="application/octet-stream"):
        arquivo = SimpleUploadedFile(nome_arquivo, conteudo, content_type=content_type)
        return DocumentoEquipamentoForm(
            data={"nome": "Manual"},
            files={"arquivo": arquivo},
        )

    def test_pdf_permitido_e_salvo(self):
        form = self._formulario("manual.pdf", PDF_MINIMO, "application/pdf")
        self.assertTrue(form.is_valid(), form.errors)
        documento = form.save(commit=False)
        documento.equipamento = self.equipamento
        documento.save()
        documento.refresh_from_db()
        self.assertTrue(documento.arquivo.name.endswith(".pdf"))
        documento.arquivo.open("rb")
        try:
            self.assertTrue(documento.arquivo.read().startswith(b"%PDF"))
        finally:
            documento.arquivo.close()

    def test_html_bloqueado(self):
        form = self._formulario("teste.html", HTML_XSS, "text/html")
        self.assertFalse(form.is_valid())
        self.assertIn("arquivo", form.errors)
        self.assertIn(MENSAGEM_TIPO_NAO_PERMITIDO, form.errors["arquivo"][0])
        self.assertEqual(DocumentoEquipamento.objects.count(), 0)

    def test_svg_bloqueado(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        form = self._formulario("teste.svg", svg, "image/svg+xml")
        self.assertFalse(form.is_valid())
        self.assertEqual(DocumentoEquipamento.objects.count(), 0)

    def test_javascript_bloqueado(self):
        form = self._formulario("teste.js", b"alert(1)", "text/javascript")
        self.assertFalse(form.is_valid())
        self.assertEqual(DocumentoEquipamento.objects.count(), 0)

    def test_pdf_uppercase_aceito(self):
        form = self._formulario("DOCUMENTO.PDF", PDF_MINIMO, "application/pdf")
        self.assertTrue(form.is_valid(), form.errors)

    def test_html_com_extensao_pdf_bloqueado(self):
        form = self._formulario("arquivo.pdf", HTML_XSS, "application/pdf")
        self.assertFalse(form.is_valid())
        self.assertIn(MENSAGEM_CONTEUDO_INVALIDO, form.errors["arquivo"][0])
        self.assertEqual(DocumentoEquipamento.objects.count(), 0)


class DocumentoDownloadSegurancaTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.sem_perm = User.objects.create_user(
            username="doc-sem-perm",
            password="teste-123",
        )
        self.com_perm = User.objects.create_user(
            username="doc-com-perm",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "equipamentos.view_equipamento",
            "equipamentos.add_documentoequipamento",
        )
        self.equipamento = Equipamento.objects.create(
            nome="Equipamento download",
            tipo="freezer",
        )
        self.documento = DocumentoEquipamento(
            equipamento=self.equipamento,
            nome="Nota",
        )
        self.documento.arquivo.save(
            "nota.pdf",
            SimpleUploadedFile("nota.pdf", PDF_MINIMO, content_type="application/pdf"),
            save=True,
        )
        self.url = reverse(
            "equipamentos:download_documento",
            args=[self.documento.pk],
        )

    def test_nao_autenticado_redireciona_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_autenticado_sem_permissao_recebe_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_com_permissao_baixa_com_headers_seguros(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        disposition = response["Content-Disposition"]
        self.assertIn("attachment", disposition.lower())
        self.assertNotIn("inline", disposition.lower())
        self.assertNotEqual(response["Content-Type"], "text/html")
        self.assertNotIn("text/html", response.get("Content-Type", ""))
        self.assertNotIn("\r", disposition)
        self.assertNotIn("\n", disposition)

    def test_upload_pela_view_rejeita_html(self):
        self.client.force_login(self.com_perm)
        url = reverse(
            "equipamentos:upload_documento",
            args=[self.equipamento.pk],
        )
        response = self.client.post(
            url,
            {
                "nome": "XSS",
                "arquivo": SimpleUploadedFile(
                    "teste.html",
                    HTML_XSS,
                    content_type="text/html",
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocumentoEquipamento.objects.count(), 1)
        self.assertContains(response, "Tipo de arquivo não permitido")


class EquipamentoFormCssTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="eq-form",
            password="teste-123",
        )
        conceder_permissoes(
            self.user,
            "equipamentos.add_equipamento",
            "equipamentos.change_equipamento",
            "equipamentos.view_equipamento",
        )
        self.client.force_login(self.user)

    def test_cadastro_carrega_css_no_head_uma_vez(self):
        response = self.client.get(reverse("equipamentos:cadastrar_equipamentos"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(html.count("equipamento_form.css"), 1)
        head, _, body = html.partition("</head>")
        self.assertIn("equipamento_form.css", head)
        self.assertNotIn("equipamento_form.css", body)

    def test_include_do_formulario_nao_tem_link_css(self):
        include = (
            Path(settings.BASE_DIR)
            / "equipamentos"
            / "templates"
            / "equipamentos"
            / "_equipamento_form.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("<link", include)
        self.assertNotIn('rel="stylesheet"', include)


class NumeroSerieUnicoTests(TestCase):

    def test_duplicata_e_rejeitada_varios_vazios_ok(self):
        Equipamento.objects.create(nome="Eq A", tipo="freezer", numero_serie="SN-1")
        Equipamento.objects.create(nome="Eq B", tipo="freezer")
        Equipamento.objects.create(nome="Eq C", tipo="freezer")
        self.assertEqual(Equipamento.objects.filter(numero_serie__isnull=True).count(), 2)
        duplicado = Equipamento(nome="Eq D", tipo="freezer", numero_serie="SN-1")
        with self.assertRaises(Exception):
            duplicado.save()


class ContratoComodatoEstaticoTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="comodato",
            password="teste-123",
        )
        conceder_permissoes(self.user, "equipamentos.view_contratocomodato")
        self.client.force_login(self.user)

    def test_lista_vazia_quando_nao_ha_contratos(self):
        from equipamentos.models import ContratoComodato

        self.assertEqual(ContratoComodato.objects.count(), 0)
        response = self.client.get(reverse("equipamentos:contrato_comodato"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nenhum contrato cadastrado")


class EquipamentoListSelectRelatedTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="eq-list",
            password="teste-123",
        )
        conceder_permissoes(self.user, "equipamentos.view_equipamento")
        self.client.force_login(self.user)
        from clientes.models import Cliente

        cliente = Cliente.objects.create(nome="Cliente lista eq")
        for i in range(3):
            Equipamento.objects.create(
                nome=f"Freezer {i}",
                tipo="freezer",
                cliente=cliente,
            )

    def test_cliente_precarregado_nao_gera_n_plus_one(self):
        from equipamentos.views import EquipamentoListView

        equipamentos = list(EquipamentoListView().get_queryset())
        with self.assertNumQueries(0):
            nomes = [
                equipamento.cliente.nome
                for equipamento in equipamentos
                if equipamento.cliente_id
            ]
        self.assertEqual(len(nomes), 3)


class EquipamentoCRUDTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="eq-crud",
            password="teste-123",
        )
        conceder_permissoes(
            self.user,
            "equipamentos.add_equipamento",
            "equipamentos.change_equipamento",
            "equipamentos.view_equipamento",
        )
        self.client.force_login(self.user)

    def test_cadastro_e_edicao(self):
        response = self.client.post(
            reverse("equipamentos:cadastrar_equipamentos"),
            {
                "nome": "Freezer CRUD",
                "tipo": "freezer",
                "status": "ativo",
                "fabricante": "",
                "numero_serie": "",
                "localizacao": "",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        eq = Equipamento.objects.get(nome="Freezer CRUD")
        self.assertIsNone(eq.numero_serie)
        response = self.client.post(
            reverse("equipamentos:editar_equipamento", args=[eq.pk]),
            {
                "nome": "Freezer CRUD editado",
                "tipo": "freezer",
                "status": "manutencao",
                "fabricante": "",
                "numero_serie": "SN-CRUD",
                "localizacao": "Pátio",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        eq.refresh_from_db()
        self.assertEqual(eq.nome, "Freezer CRUD editado")
        self.assertEqual(eq.status, "manutencao")
        self.assertEqual(eq.numero_serie, "SN-CRUD")


class ContratoComodatoPersistenciaTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="comodato-ok",
            password="teste-123",
        )
        conceder_permissoes(
            self.user,
            "equipamentos.view_contratocomodato",
            "equipamentos.add_contratocomodato",
            "equipamentos.change_contratocomodato",
        )
        self.sem_perm = User.objects.create_user(
            username="comodato-sem",
            password="teste-123",
        )
        self.cliente = Cliente.objects.create(
            nome="Cliente comodato",
            cnpj="12.345.678/0001-99",
            cidade="Campinas",
        )
        self.equipamento = Equipamento.objects.create(
            nome="Conservador comodato",
            tipo="freezer",
            cliente=self.cliente,
        )
        self.client.force_login(self.user)

    def _payload(self, numero="COM-001"):
        return {
            "numero_contrato": numero,
            "cliente": self.cliente.pk,
            "equipamento": self.equipamento.pk,
            "data_inicio": "2026-09-01",
            "data_fim": "",
            "status": "ativo",
            "observacoes": "Observação operacional",
        }

    def test_modelo_relacionamentos_status_timestamps(self):
        contrato = ContratoComodato.objects.create(
            cliente=self.cliente,
            equipamento=self.equipamento,
            numero_contrato="COM-MOD",
            data_inicio=date(2026, 1, 10),
            status="encerrado",
        )
        self.assertEqual(contrato.cliente, self.cliente)
        self.assertEqual(contrato.equipamento, self.equipamento)
        self.assertEqual(contrato.status, "encerrado")
        self.assertIsNotNone(contrato.criado_em)
        self.assertIsNotNone(contrato.atualizado_em)

    def test_historico_permite_varios_contratos_no_mesmo_equipamento(self):
        ContratoComodato.objects.create(
            cliente=self.cliente,
            equipamento=self.equipamento,
            numero_contrato="COM-A",
            data_inicio=date(2025, 1, 1),
            status="encerrado",
        )
        ContratoComodato.objects.create(
            cliente=self.cliente,
            equipamento=self.equipamento,
            numero_contrato="COM-B",
            data_inicio=date(2026, 1, 1),
            status="ativo",
        )
        self.assertEqual(
            ContratoComodato.objects.filter(equipamento=self.equipamento).count(),
            2,
        )

    def test_formulario_valido_e_obrigatorios(self):
        form = ContratoComodatoForm(data=self._payload())
        self.assertTrue(form.is_valid(), form.errors)
        form_vazio = ContratoComodatoForm(data={})
        self.assertFalse(form_vazio.is_valid())
        self.assertIn("cliente", form_vazio.errors)
        self.assertIn("equipamento", form_vazio.errors)
        self.assertIn("numero_contrato", form_vazio.errors)
        self.assertIn("data_inicio", form_vazio.errors)

    def test_anonimo_redireciona_login(self):
        self.client.logout()
        response = self.client.get(reverse("equipamentos:contrato_comodato"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_sem_permissao_recebe_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("equipamentos:contrato_comodato"))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse("equipamentos:contrato_comodato_novo"))
        self.assertEqual(response.status_code, 403)

    def test_criacao_persiste_e_detalhe_exibe(self):
        response = self.client.post(
            reverse("equipamentos:contrato_comodato_novo"),
            self._payload(),
        )
        self.assertEqual(response.status_code, 302)
        contrato = ContratoComodato.objects.get(numero_contrato="COM-001")
        self.assertEqual(contrato.cliente, self.cliente)
        self.assertEqual(contrato.equipamento, self.equipamento)
        detalhe = self.client.get(
            reverse("equipamentos:contrato_comodato_detalhe", args=[contrato.pk])
        )
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, "COM-001")
        self.assertContains(detalhe, "Cliente comodato")
        self.assertContains(detalhe, "Conservador comodato")
        self.assertContains(detalhe, "onclick=\"window.print()\"")
        self.assertContains(detalhe, "contrato-comodato")
        self.assertContains(detalhe, "gs-print-comodato")
        self.assertContains(detalhe, "css/contrato_comodato.css")
        self.assertContains(detalhe, "img/logo-gelosar.jpg")
        self.assertContains(detalhe, "logo-oficial")

    def test_edicao_mantem_criado_em(self):
        contrato = ContratoComodato.objects.create(
            cliente=self.cliente,
            equipamento=self.equipamento,
            numero_contrato="COM-ED",
            data_inicio=date(2026, 2, 1),
        )
        criado = contrato.criado_em
        payload = self._payload("COM-ED")
        payload["status"] = "encerrado"
        payload["observacoes"] = "Encerrado"
        response = self.client.post(
            reverse("equipamentos:contrato_comodato_editar", args=[contrato.pk]),
            payload,
        )
        self.assertEqual(response.status_code, 302)
        contrato.refresh_from_db()
        self.assertEqual(contrato.status, "encerrado")
        self.assertEqual(contrato.criado_em, criado)

    def test_protect_impede_excluir_cliente_e_equipamento(self):
        ContratoComodato.objects.create(
            cliente=self.cliente,
            equipamento=self.equipamento,
            numero_contrato="COM-PROT",
            data_inicio=date(2026, 3, 1),
        )
        with self.assertRaises(ProtectedError):
            self.cliente.delete()
        with self.assertRaises(ProtectedError):
            self.equipamento.delete()

    def test_admin_lista_campos_principais(self):
        admin = ContratoComodatoAdmin(ContratoComodato, site)
        self.assertIn("numero_contrato", admin.list_display)
        self.assertIn("cliente", admin.list_display)
        self.assertIn("equipamento", admin.list_display)
        self.assertIn("status", admin.list_display)
        self.assertIn("criado_em", admin.readonly_fields)
