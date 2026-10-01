from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from core.charts import (
    compras_cliente_por_mes,
    estoque_atual_gelo,
    mix_produtos_cliente,
    producao_por_dia,
    vendas_por_dia,
)
from equipamentos.models import Equipamento
from estoque.models import MovimentacaoProduto
from producao.models import Producao
from produtos.models import Produto
from vendas.models import ItemVenda, Venda


class ChartsTests(TestCase):

    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente gráfico")
        self.produto_5 = Produto.objects.create(
            nome="Gelo 5kg gráfico",
            peso_kg=Decimal("5.00"),
            preco_venda=Decimal("6.00"),
        )
        self.produto_3 = Produto.objects.create(
            nome="Gelo 3kg gráfico",
            peso_kg=Decimal("3.00"),
            preco_venda=Decimal("5.00"),
        )
        self.equipamento = Equipamento.objects.create(
            nome="Máquina gráfico",
            tipo="maquina_gelo",
        )

    def _criar_venda(self, data_venda, produto, quantidade):
        venda = Venda.objects.create(cliente=self.cliente)
        Venda.objects.filter(pk=venda.pk).update(data=data_venda)
        venda.refresh_from_db()
        ItemVenda.objects.create(
            venda=venda,
            produto=produto,
            quantidade=quantidade,
        )
        return venda

    def test_vendas_por_dia_sem_vendas_retorna_zeros(self):
        dados = vendas_por_dia(dias=7)
        self.assertEqual(len(dados["labels"]), 7)
        self.assertEqual(dados["values"], [0, 0, 0, 0, 0, 0, 0])

    def test_vendas_por_dia_agrega_total_do_dia(self):
        hoje = timezone.localdate()
        self._criar_venda(hoje, self.produto_5, 10)
        self._criar_venda(hoje, self.produto_3, 4)
        dados = vendas_por_dia(dias=7)
        self.assertEqual(dados["values"][-1], 80.0)

    def test_producao_por_dia_sem_registros_retorna_zeros(self):
        dados = producao_por_dia(dias=7)
        self.assertEqual(dados["datasets"][0]["data"], [0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(dados["datasets"][1]["data"], [0, 0, 0, 0, 0, 0, 0])

    def test_producao_por_dia_separa_3kg_e_5kg(self):
        agora = timezone.now()
        Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto_5,
            quantidade=20,
        )
        Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto_3,
            quantidade=8,
        )
        Producao.objects.filter(produto=self.produto_5).update(data_hora=agora)
        Producao.objects.filter(produto=self.produto_3).update(data_hora=agora)
        dados = producao_por_dia(dias=7)
        self.assertEqual(dados["datasets"][0]["data"][-1], 8)
        self.assertEqual(dados["datasets"][1]["data"][-1], 20)

    def test_estoque_atual_usa_service(self):
        MovimentacaoProduto.objects.create(
            produto=self.produto_5,
            tipo="ENTRADA",
            quantidade=15,
        )
        dados = estoque_atual_gelo()
        self.assertEqual(dados["labels"], ["Gelo 5kg", "Gelo 3kg"])
        self.assertEqual(dados["values"][0], 15)
        self.assertEqual(dados["values"][1], 0)

    def test_compras_cliente_por_mes_vazio(self):
        dados = compras_cliente_por_mes(self.cliente, meses=6)
        self.assertEqual(len(dados["labels"]), 6)
        self.assertEqual(dados["values"], [0, 0, 0, 0, 0, 0])

    def test_mix_produtos_cliente(self):
        dados = mix_produtos_cliente({"Gelo 5kg": 10, "Gelo 3kg": 3})
        self.assertEqual(dados["labels"], ["Gelo 5kg", "Gelo 3kg"])
        self.assertEqual(dados["values"], [10.0, 3.0])


class DashboardViewChartsTests(TestCase):

    def setUp(self):
        from accounts.test_utils import conceder_permissoes

        User = get_user_model()
        self.user = User.objects.create_user(
            username="dash",
            password="teste-123",
        )
        conceder_permissoes(
            self.user,
            "equipamentos.view_equipamento",
            "producao.view_producao",
            "estoque.view_movimentacaoproduto",
            "vendas.view_venda",
        )
        self.client.force_login(self.user)

    def test_dashboard_carrega_com_graficos_vazios(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("chart_vendas", response.context)
        self.assertEqual(len(response.context["chart_vendas"]["labels"]), 7)
        self.assertNotContains(response, "Total Maquinário")
        self.assertNotContains(response, "Produção acumulada")
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertNotContains(response, 'id="chart-producao"')
        self.assertNotContains(response, 'id="chart-estoque"')
        self.assertContains(response, "Produtos acabados (gelo)")
        self.assertContains(response, "Gelo 5kg")
        self.assertContains(response, "dashboard_charts.js")
        self.assertContains(response, "js/vendor/chart.umd.min.js")
        self.assertContains(response, "img/logo-gelosar.jpg")

    def test_dashboard_com_producao_sem_vendas_omite_grafico_de_vendas(self):
        equipamento = Equipamento.objects.create(
            nome="Máquina dashboard",
            tipo="maquina_gelo",
        )
        produto = Produto.objects.create(
            nome="Gelo dashboard produção",
            peso_kg=Decimal("5.00"),
            preco_venda="1.00",
        )
        Producao.objects.create(
            equipamento=equipamento,
            produto=produto,
            quantidade=4,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chart-producao"')
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertContains(response, "Produção acumulada")

    def test_dashboard_com_dados_mostra_graficos_e_kpis(self):
        equipamento = Equipamento.objects.create(
            nome="Máquina dashboard cheio",
            tipo="maquina_gelo",
            status="ativo",
        )
        produto = Produto.objects.create(
            nome="Gelo dashboard cheio",
            peso_kg=Decimal("5.00"),
            preco_venda="2.00",
        )
        Producao.objects.create(
            equipamento=equipamento,
            produto=produto,
            quantidade=3,
        )
        cliente = Cliente.objects.create(nome="Cliente dashboard cheio")
        venda = Venda.objects.create(cliente=cliente)
        ItemVenda.objects.create(venda=venda, produto=produto, quantidade=Decimal("2"))
        MovimentacaoProduto.objects.create(
            produto=produto,
            tipo="ENTRADA",
            quantidade=6,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chart-vendas"')
        self.assertContains(response, 'id="chart-producao"')
        self.assertContains(response, 'id="chart-estoque"')
        self.assertEqual(response.context["total_equipamentos"], 1)
        self.assertEqual(response.context["ativos"], 1)
        self.assertGreater(response.context["producao_hoje"], 0)
        self.assertContains(response, "Gelo 5kg")


class DashboardEquipamentosKpiTests(TestCase):

    def setUp(self):
        from accounts.test_utils import conceder_permissoes

        User = get_user_model()
        self.user = User.objects.create_user(
            username="dash-kpi",
            password="teste-123",
        )
        conceder_permissoes(self.user, "equipamentos.view_equipamento")
        self.client.force_login(self.user)
        Equipamento.objects.create(nome="Ativo KPI", tipo="freezer", status="ativo")
        Equipamento.objects.create(
            nome="Manutencao KPI",
            tipo="freezer",
            status="manutencao",
        )
        Equipamento.objects.create(nome="Parado KPI", tipo="freezer", status="parado")

    def test_kpi_usa_status_reais_do_model(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["ativos"], 1)
        self.assertEqual(response.context["manutencao"], 1)
        self.assertEqual(response.context["parados"], 1)
        self.assertEqual(response.context["inativos"], 1)
        self.assertEqual(response.context["total_equipamentos"], 3)
        self.assertContains(response, "Parados")
        self.assertNotContains(response, 'status="inativo"')


class DashboardPermissaoBlocosTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="dash-perm",
            password="teste-123",
        )
        self.client.force_login(self.user)
        self.equipamento = Equipamento.objects.create(
            nome="Máquina perm",
            tipo="maquina_gelo",
            status="ativo",
        )
        self.produto = Produto.objects.create(
            nome="Gelo perm",
            peso_kg=Decimal("5.00"),
            preco_venda="2.00",
        )
        Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto,
            quantidade=3,
        )
        cliente = Cliente.objects.create(nome="Cliente perm")
        venda = Venda.objects.create(cliente=cliente)
        ItemVenda.objects.create(
            venda=venda,
            produto=self.produto,
            quantidade=Decimal("2"),
        )
        MovimentacaoProduto.objects.create(
            produto=self.produto,
            tipo="ENTRADA",
            quantidade=6,
        )

    def _conceder(self, *permissoes):
        from accounts.test_utils import conceder_permissoes

        conceder_permissoes(self.user, *permissoes)

    def _get(self):
        return self.client.get(reverse("dashboard"))

    def test_sem_permissao_acessa_sem_blocos_operacionais(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visão geral da operação da fábrica de gelo")
        self.assertContains(response, "dashboard_charts.js")
        for chave in (
            "total_equipamentos",
            "producao_hoje",
            "chart_producao",
            "estoque_5kg_sacos",
            "chart_estoque",
            "chart_vendas",
        ):
            self.assertNotIn(chave, response.context)
        self.assertNotContains(response, "Total Maquinário")
        self.assertNotContains(response, "Produção acumulada")
        self.assertNotContains(response, "Produtos acabados (gelo)")
        self.assertNotContains(response, "Insumos (embalagens)")
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertNotContains(response, 'id="chart-producao"')
        self.assertNotContains(response, 'id="chart-estoque"')
        self.assertNotContains(response, "chart-vendas-data")

    def test_permissao_de_estoque_mostra_gelo_embalagens_e_grafico(self):
        self._conceder("estoque.view_movimentacaoproduto")
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produtos acabados (gelo)")
        self.assertContains(response, "Insumos (embalagens)")
        self.assertContains(response, 'id="chart-estoque"')
        self.assertEqual(response.context["estoque_5kg_sacos"], 6)
        self.assertIsInstance(response.context["estoque_5kg_sacos"], int)
        self.assertIsInstance(response.context["chart_estoque"]["values"][0], int)
        self.assertNotContains(response, "6,00")
        self.assertNotContains(response, "6.00")
        self.assertNotContains(response, "Total Maquinário")
        self.assertNotContains(response, "Produção acumulada")
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertNotContains(response, 'id="chart-producao"')
        self.assertNotIn("chart_vendas", response.context)
        self.assertNotIn("total_equipamentos", response.context)

    def test_permissao_de_producao_mostra_kpis_e_grafico(self):
        self._conceder("producao.view_producao")
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produção acumulada")
        self.assertContains(response, 'id="chart-producao"')
        self.assertGreater(response.context["producao_hoje"], 0)
        self.assertIsInstance(response.context["producao_hoje"], int)
        self.assertNotContains(response, "3,00")
        self.assertNotContains(response, "Produtos acabados (gelo)")
        self.assertNotContains(response, "Total Maquinário")
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertNotContains(response, 'id="chart-estoque"')

    def test_permissao_de_vendas_mostra_grafico(self):
        self._conceder("vendas.view_venda")
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chart-vendas"')
        self.assertContains(response, "Vendas (7 dias)")
        self.assertIn("chart_vendas", response.context)
        self.assertTrue(response.context["chart_vendas"]["currency"])
        self.assertTrue(
            all(isinstance(valor, float) for valor in response.context["chart_vendas"]["values"])
        )
        self.assertNotContains(response, "Produção acumulada")
        self.assertNotContains(response, "Produtos acabados (gelo)")
        self.assertNotContains(response, "Total Maquinário")
        self.assertNotContains(response, 'id="chart-producao"')
        self.assertNotContains(response, 'id="chart-estoque"')

    def test_permissao_de_equipamentos_mostra_kpis(self):
        self._conceder("equipamentos.view_equipamento")
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Maquinário")
        self.assertEqual(response.context["total_equipamentos"], 1)
        self.assertEqual(response.context["ativos"], 1)
        self.assertNotContains(response, "Produção acumulada")
        self.assertNotContains(response, "Produtos acabados (gelo)")
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertNotContains(response, 'id="chart-producao"')
        self.assertNotContains(response, 'id="chart-estoque"')

    def test_varias_permissoes_mostram_os_blocos_correspondentes(self):
        self._conceder(
            "estoque.view_movimentacaoproduto",
            "producao.view_producao",
        )
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produtos acabados (gelo)")
        self.assertContains(response, "Produção acumulada")
        self.assertContains(response, 'id="chart-estoque"')
        self.assertContains(response, 'id="chart-producao"')
        self.assertNotContains(response, "Total Maquinário")
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertNotIn("chart_vendas", response.context)
        self.assertNotIn("total_equipamentos", response.context)

    def test_superusuario_ve_todos_os_blocos(self):
        User = get_user_model()
        superuser = User.objects.create_superuser(
            username="dash-super",
            password="teste-123",
        )
        self.client.force_login(superuser)
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Maquinário")
        self.assertContains(response, "Produção acumulada")
        self.assertContains(response, "Produtos acabados (gelo)")
        self.assertContains(response, "Insumos (embalagens)")
        self.assertContains(response, 'id="chart-vendas"')
        self.assertContains(response, 'id="chart-producao"')
        self.assertContains(response, 'id="chart-estoque"')

    def test_estoque_zerado_continua_visivel_para_quem_pode_ver(self):
        from accounts.test_utils import conceder_permissoes

        ItemVenda.objects.all().delete()
        Venda.objects.all().delete()
        Producao.objects.all().delete()
        MovimentacaoProduto.objects.all().delete()
        Equipamento.objects.all().delete()
        User = get_user_model()
        autorizado = User.objects.create_user(
            username="dash-vazio",
            password="teste-123",
        )
        conceder_permissoes(
            autorizado,
            "equipamentos.view_equipamento",
            "producao.view_producao",
            "estoque.view_movimentacaoproduto",
            "vendas.view_venda",
        )
        self.client.force_login(autorizado)
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produtos acabados (gelo)")
        self.assertContains(response, "Gelo 5kg")
        self.assertContains(response, "Insumos (embalagens)")
        self.assertEqual(response.context["estoque_5kg_sacos"], 0)
        self.assertEqual(response.context["estoque_3kg_sacos"], 0)
        self.assertNotContains(response, "Total Maquinário")
        self.assertNotContains(response, "Produção acumulada")
        self.assertNotContains(response, 'id="chart-vendas"')
        self.assertNotContains(response, 'id="chart-producao"')
        self.assertNotContains(response, 'id="chart-estoque"')
        self.assertContains(response, "dashboard_charts.js")


class LogoReferenciasTests(SimpleTestCase):

    def test_templates_apontam_para_logo_existente(self):
        from django.contrib.staticfiles import finders

        base = Path(settings.BASE_DIR)
        logo = base / "static" / "img" / "logo-gelosar.jpg"
        self.assertTrue(logo.exists(), "static/img/logo-gelosar.jpg deve existir")
        self.assertTrue(finders.find("img/logo-gelosar.jpg"))
        for relativo in (
            "templates/base.html",
            "accounts/templates/registration/login.html",
        ):
            texto = (base / relativo).read_text(encoding="utf-8")
            self.assertIn("img/logo-gelosar.jpg", texto)
            self.assertNotIn("logo-gelosar.jpeg", texto)


class TokensFormularioCssTests(SimpleTestCase):

    def test_css_de_formulario_nao_redefine_root(self):
        base = Path(settings.BASE_DIR)
        cliente = (
            base / "clientes" / "static" / "cliente" / "css" / "cliente_form.css"
        ).read_text(encoding="utf-8")
        equipamento = (
            base / "equipamentos" / "static" / "css" / "equipamento_form.css"
        ).read_text(encoding="utf-8")
        global_css = (base / "static" / "css" / "base.css").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(":root {", cliente)
        self.assertNotIn(":root {", equipamento)
        self.assertNotIn("#0d6efd", cliente)
        self.assertNotIn("#0d6efd", equipamento)
        self.assertIn(":root {", global_css)
        self.assertIn("--gs-primary:", global_css)


class DjangoSecuritySettingsTests(SimpleTestCase):

    def test_desenvolvimento_sem_variaveis_permite_debug(self):
        from config.settings import resolve_debug, resolve_secret_key

        environ = {}
        debug = resolve_debug(environ)
        self.assertTrue(debug)
        self.assertTrue(
            resolve_secret_key(environ, debug=debug, production=False)
        )

    def test_debug_explicito_true(self):
        from config.settings import resolve_debug

        for valor in ("true", "True", "1", "yes", "on"):
            self.assertTrue(resolve_debug({"DJANGO_DEBUG": valor}))

    def test_debug_explicito_false(self):
        from config.settings import resolve_debug

        for valor in ("false", "False", "0", "no", "off"):
            self.assertFalse(resolve_debug({"DJANGO_DEBUG": valor}))

    def test_producao_debug_false_sem_secret_key_falha(self):
        from config.settings import resolve_secret_key
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            resolve_secret_key(
                {},
                debug=False,
                production=False,
            )

    def test_producao_com_secret_key_carrega(self):
        from config.settings import resolve_debug, resolve_secret_key

        chave_ficticia = "test-only-not-a-real-secret-key"
        environ = {
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": chave_ficticia,
        }
        debug = resolve_debug(environ)
        self.assertFalse(debug)
        self.assertEqual(
            resolve_secret_key(environ, debug=debug, production=False),
            chave_ficticia,
        )

    def test_environment_production_sem_secret_key_falha(self):
        from config.settings import (
            is_production_environment,
            resolve_debug,
            resolve_secret_key,
        )
        from django.core.exceptions import ImproperlyConfigured

        environ = {"DJANGO_ENVIRONMENT": "production"}
        self.assertTrue(is_production_environment(environ))
        self.assertFalse(resolve_debug(environ))
        with self.assertRaises(ImproperlyConfigured):
            resolve_secret_key(
                environ,
                debug=False,
                production=True,
            )

    def test_booleanos_invalidos_falham(self):
        from config.settings import parse_env_bool
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            parse_env_bool("talvez")


class DatabaseConfigTests(SimpleTestCase):

    def test_desenvolvimento_sem_url_usa_sqlite(self):
        from config.database import SQLITE_ENGINE, resolve_database

        databases = resolve_database({}, production=False, base_dir=settings.BASE_DIR)
        self.assertEqual(databases["default"]["ENGINE"], SQLITE_ENGINE)
        self.assertEqual(databases["default"]["CONN_MAX_AGE"], 0)
        self.assertTrue(str(databases["default"]["NAME"]).endswith("db.sqlite3"))

    def test_postgres_url_e_reconhecida(self):
        from config.database import POSTGRES_ENGINE, parse_database_url

        config = parse_database_url(
            "postgres://gelo_user:s3nha%40x@db.example:6543/gelosar?sslmode=require"
        )
        self.assertEqual(config["ENGINE"], POSTGRES_ENGINE)
        self.assertEqual(config["NAME"], "gelosar")
        self.assertEqual(config["USER"], "gelo_user")
        self.assertEqual(config["PASSWORD"], "s3nha@x")
        self.assertEqual(config["HOST"], "db.example")
        self.assertEqual(config["PORT"], "6543")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")

    def test_producao_sem_database_url_falha(self):
        from config.database import resolve_database
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            resolve_database({}, production=True, base_dir=settings.BASE_DIR)

    def test_producao_nao_aceita_sqlite(self):
        from config.database import resolve_database
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            resolve_database(
                {"DATABASE_URL": "sqlite:///tmp/gelosar.sqlite3"},
                production=True,
                base_dir=settings.BASE_DIR,
            )

    def test_postgres_conn_max_age_padrao(self):
        from config.database import POSTGRES_CONN_MAX_AGE_PADRAO, resolve_database

        databases = resolve_database(
            {"DATABASE_URL": "postgres://u:p@localhost:5432/gelosar"},
            production=True,
            base_dir=settings.BASE_DIR,
        )
        self.assertEqual(
            databases["default"]["CONN_MAX_AGE"],
            POSTGRES_CONN_MAX_AGE_PADRAO,
        )

    def test_codigo_nao_contem_credencial_real(self):
        texto = (Path(settings.BASE_DIR) / "config" / "settings.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("postgres://", texto.lower())
        self.assertNotIn("postgresql://", texto.lower())
        env_example = (Path(settings.BASE_DIR) / ".env.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("DATABASE_URL=", env_example)
        self.assertNotIn("postgres://", env_example)


class DependenciasEChartLocalTests(SimpleTestCase):

    def test_requirements_txt_existe_com_django(self):
        texto = (Path(settings.BASE_DIR) / "requirements.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("Django==", texto)

    def test_chartjs_local_existe(self):
        arquivo = (
            Path(settings.BASE_DIR) / "static" / "js" / "vendor" / "chart.umd.min.js"
        )
        self.assertTrue(arquivo.exists())
        self.assertGreater(arquivo.stat().st_size, 1000)


class ProducaoDiaDashboardEListaTests(TestCase):

    def setUp(self):
        from accounts.test_utils import conceder_permissoes

        User = get_user_model()
        self.user = User.objects.create_user(
            username="prod-dia",
            password="teste-123",
        )
        conceder_permissoes(self.user, "producao.view_producao")
        self.client.force_login(self.user)
        self.equipamento = Equipamento.objects.create(
            nome="Máquina dia",
            tipo="maquina_gelo",
        )
        self.produto = Produto.objects.create(
            nome="Gelo dia",
            peso_kg=Decimal("5.00"),
            preco_venda="1.00",
        )

    def test_dashboard_e_lista_usam_o_mesmo_dia_local(self):
        from datetime import timedelta

        from core.periodo import intervalo_dia_local

        inicio, _fim = intervalo_dia_local()
        producao = Producao.objects.create(
            equipamento=self.equipamento,
            produto=self.produto,
            quantidade=7,
        )
        Producao.objects.filter(pk=producao.pk).update(
            data_hora=inicio + timedelta(hours=2)
        )
        dash = self.client.get(reverse("dashboard"))
        lista = self.client.get(reverse("producao:producao_list"))
        self.assertEqual(dash.context["producao_hoje"], 7)
        self.assertEqual(lista.context["producao_hoje"], 7)
        self.assertEqual(
            dash.context["producao_hoje"],
            lista.context["producao_hoje"],
        )


class QuantidadeSemDecimalTests(SimpleTestCase):

    def test_inteiro_exato_perde_casas_decimais(self):
        from core.numeros import quantidade_sem_decimal

        self.assertEqual(quantidade_sem_decimal(Decimal("25.00")), 25)
        self.assertEqual(quantidade_sem_decimal(Decimal("100.00")), 100)
        self.assertEqual(quantidade_sem_decimal(25), 25)
        self.assertIsInstance(quantidade_sem_decimal(Decimal("25.00")), int)

    def test_fracao_real_permanece(self):
        from core.numeros import quantidade_sem_decimal

        self.assertEqual(quantidade_sem_decimal(Decimal("25.50")), Decimal("25.50"))

    def test_moeda_continua_com_centavos(self):
        template = Template("{% load moeda %}{{ valor|moeda_br }}")
        html = template.render(Context({"valor": Decimal("25.00")}))
        self.assertEqual(html, "R$ 25,00")
