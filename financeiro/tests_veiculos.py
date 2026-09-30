from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from accounts.test_utils import conceder_permissoes
from financeiro.models import (
    CategoriaFinanceira,
    ContaPagar,
    Fornecedor,
    ManutencaoVeiculo,
    ObrigacaoVeiculo,
    PlanoManutencao,
    Veiculo,
)
from financeiro.services.ipva import (
    MOTIVO_ANO_AUSENTE,
    REGRAS_ISENCAO_IPVA,
    SITUACAO_DEVIDO,
    SITUACAO_ISENTO,
    SITUACAO_NAO_DETERMINADO,
    avaliar_ipva,
)
from financeiro.services.manutencao import (
    SITUACAO_ATRASADA,
    SITUACAO_EM_DIA,
    SITUACAO_PROXIMA,
    SITUACAO_SEM_HISTORICO,
    calcular_situacao_plano,
)
from financeiro.services.obrigacoes_veiculo import (
    gerar_obrigacoes_exercicio,
    gerar_obrigacoes_frota,
)

PDF_MINIMO = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


def criar_veiculo(**kwargs):
    dados = {
        "marca": "Fiat",
        "modelo": "Fiorino",
        "placa": "ABC1D23",
        "ano_fabricacao": 2018,
        "ano_modelo": 2019,
        "uf": "SP",
        "km_atual": 50000,
    }
    dados.update(kwargs)
    return Veiculo.objects.create(**dados)


class VeiculoModelTests(TestCase):
    def test_criacao_normaliza_placa(self):
        veiculo = criar_veiculo(placa="abc-1d23")
        self.assertEqual(veiculo.placa, "ABC1D23")
        self.assertEqual(veiculo.placa_formatada, "ABC1D23")

    def test_placa_antiga_formatada(self):
        veiculo = criar_veiculo(placa="abc-1234")
        self.assertEqual(veiculo.placa, "ABC1234")
        self.assertEqual(veiculo.placa_formatada, "ABC-1234")

    def test_placa_unica(self):
        criar_veiculo(placa="ABC1D23")
        with self.assertRaises(IntegrityError):
            criar_veiculo(placa="ABC1D23", modelo="Uno")

    def test_placa_invalida(self):
        veiculo = Veiculo(
            marca="Fiat",
            modelo="Uno",
            placa="123",
            ano_fabricacao=2010,
            ano_modelo=2010,
        )
        with self.assertRaises(ValidationError):
            veiculo.full_clean()

    def test_ano_modelo_anterior_fabricacao(self):
        veiculo = Veiculo(
            marca="Fiat",
            modelo="Uno",
            placa="AAA1B23",
            ano_fabricacao=2020,
            ano_modelo=2019,
        )
        with self.assertRaises(ValidationError):
            veiculo.full_clean()

    def test_km_invalida(self):
        veiculo = Veiculo(
            marca="Fiat",
            modelo="Uno",
            placa="AAA1B24",
            ano_fabricacao=2010,
            ano_modelo=2010,
            km_atual=-10,
        )
        with self.assertRaises(ValidationError):
            veiculo.full_clean()

    def test_km_nao_pode_diminuir(self):
        veiculo = criar_veiculo(km_atual=10000)
        veiculo.km_atual = 9000
        with self.assertRaises(ValidationError) as contexto:
            veiculo.full_clean()
        self.assertIn("km_atual", contexto.exception.error_dict)
        veiculo.km_atual = 10500
        veiculo.full_clean()

    def test_uf_padrao_sp(self):
        veiculo = criar_veiculo()
        self.assertEqual(veiculo.uf, "SP")

    def test_inativacao(self):
        veiculo = criar_veiculo()
        veiculo.ativo = False
        veiculo.save()
        veiculo.refresh_from_db()
        self.assertFalse(veiculo.ativo)

    def test_nao_exclui_com_relacionados(self):
        veiculo = criar_veiculo()
        PlanoManutencao.objects.create(
            veiculo=veiculo,
            nome="Óleo",
            intervalo_km=10000,
        )
        with self.assertRaises(ProtectedError):
            veiculo.delete()


class PlanoManutencaoTests(TestCase):
    def setUp(self):
        self.veiculo = criar_veiculo()

    def test_intervalo_km(self):
        plano = PlanoManutencao(
            veiculo=self.veiculo, nome="Óleo", intervalo_km=10000
        )
        plano.full_clean()
        plano.save()
        self.assertEqual(plano.intervalo_km, 10000)

    def test_intervalo_meses(self):
        plano = PlanoManutencao(
            veiculo=self.veiculo, nome="Revisão", intervalo_meses=12
        )
        plano.full_clean()
        plano.save()

    def test_ambos_intervalos(self):
        plano = PlanoManutencao(
            veiculo=self.veiculo,
            nome="Óleo",
            intervalo_km=10000,
            intervalo_meses=12,
        )
        plano.full_clean()
        plano.save()

    def test_sem_intervalo(self):
        plano = PlanoManutencao(veiculo=self.veiculo, nome="Inválido")
        with self.assertRaises(ValidationError):
            plano.full_clean()

    def test_intervalo_invalido(self):
        plano = PlanoManutencao(
            veiculo=self.veiculo, nome="Inválido", intervalo_km=0
        )
        with self.assertRaises(ValidationError):
            plano.full_clean()


class ManutencaoVeiculoTests(TestCase):
    def setUp(self):
        self.veiculo = criar_veiculo(km_atual=50000)
        self.outro = criar_veiculo(placa="XYZ1A23", km_atual=1000)
        self.plano = PlanoManutencao.objects.create(
            veiculo=self.veiculo,
            nome="Óleo",
            intervalo_km=10000,
            intervalo_meses=12,
            antecedencia_alerta_km=1000,
            antecedencia_alerta_dias=30,
        )
        self.fornecedor = Fornecedor.objects.create(nome="Oficina Central")

    def test_criacao_com_fornecedor_e_plano(self):
        manutencao = ManutencaoVeiculo.objects.create(
            veiculo=self.veiculo,
            plano=self.plano,
            fornecedor=self.fornecedor,
            data_realizacao=date(2026, 1, 1),
            km_realizacao=50000,
            descricao="Troca de óleo",
        )
        self.assertEqual(manutencao.fornecedor, self.fornecedor)
        self.assertEqual(manutencao.plano, self.plano)

    def test_plano_de_outro_veiculo(self):
        plano_outro = PlanoManutencao.objects.create(
            veiculo=self.outro, nome="Freio", intervalo_km=20000
        )
        manutencao = ManutencaoVeiculo(
            veiculo=self.veiculo,
            plano=plano_outro,
            data_realizacao=date(2026, 1, 1),
            km_realizacao=50000,
            descricao="Erro",
        )
        with self.assertRaises(ValidationError):
            manutencao.full_clean()

    def test_atualiza_km_maior(self):
        ManutencaoVeiculo.objects.create(
            veiculo=self.veiculo,
            data_realizacao=date(2026, 2, 1),
            km_realizacao=52000,
            descricao="Eventual",
        )
        self.veiculo.refresh_from_db()
        self.assertEqual(self.veiculo.km_atual, 52000)

    def test_nao_reduz_km(self):
        ManutencaoVeiculo.objects.create(
            veiculo=self.veiculo,
            data_realizacao=date(2026, 2, 1),
            km_realizacao=40000,
            descricao="Anterior",
        )
        self.veiculo.refresh_from_db()
        self.assertEqual(self.veiculo.km_atual, 50000)


class CalculoManutencaoTests(TestCase):
    def setUp(self):
        self.veiculo = criar_veiculo(km_atual=50500)
        self.plano = PlanoManutencao.objects.create(
            veiculo=self.veiculo,
            nome="Óleo",
            intervalo_km=10000,
            intervalo_meses=12,
            antecedencia_alerta_km=1000,
            antecedencia_alerta_dias=30,
        )
        self.ultima = ManutencaoVeiculo.objects.create(
            veiculo=self.veiculo,
            plano=self.plano,
            data_realizacao=date(2026, 1, 1),
            km_realizacao=50000,
            descricao="Óleo",
        )

    def test_em_dia(self):
        self.veiculo.km_atual = 50500
        situacao = calcular_situacao_plano(
            self.plano, veiculo=self.veiculo, hoje=date(2026, 2, 1)
        )
        self.assertEqual(situacao.situacao, SITUACAO_EM_DIA)
        self.assertEqual(situacao.proxima_km, 60000)
        self.assertEqual(situacao.proxima_data, date(2027, 1, 1))

    def test_proxima_por_km(self):
        self.veiculo.km_atual = 59500
        situacao = calcular_situacao_plano(
            self.plano, veiculo=self.veiculo, hoje=date(2026, 6, 1)
        )
        self.assertEqual(situacao.situacao, SITUACAO_PROXIMA)

    def test_proxima_por_data(self):
        self.veiculo.km_atual = 50500
        situacao = calcular_situacao_plano(
            self.plano, veiculo=self.veiculo, hoje=date(2026, 12, 20)
        )
        self.assertEqual(situacao.situacao, SITUACAO_PROXIMA)

    def test_atrasada_por_km(self):
        self.veiculo.km_atual = 60500
        situacao = calcular_situacao_plano(
            self.plano, veiculo=self.veiculo, hoje=date(2026, 6, 1)
        )
        self.assertEqual(situacao.situacao, SITUACAO_ATRASADA)

    def test_atrasada_por_data(self):
        self.veiculo.km_atual = 50500
        situacao = calcular_situacao_plano(
            self.plano, veiculo=self.veiculo, hoje=date(2027, 2, 2)
        )
        self.assertEqual(situacao.situacao, SITUACAO_ATRASADA)

    def test_sem_historico(self):
        self.ultima.delete()
        self.veiculo.km_atual = 50000
        situacao = calcular_situacao_plano(
            self.plano, veiculo=self.veiculo, hoje=date(2026, 6, 1)
        )
        self.assertEqual(situacao.situacao, SITUACAO_SEM_HISTORICO)


class ContaPagarVeiculoTests(TestCase):
    def setUp(self):
        self.veiculo = criar_veiculo()
        self.categoria = CategoriaFinanceira.objects.get(slug="manutencao")
        self.manutencao = ManutencaoVeiculo.objects.create(
            veiculo=self.veiculo,
            data_realizacao=date(2026, 3, 1),
            km_realizacao=51000,
            descricao="Revisão completa",
        )

    def _conta(self, descricao, valor, **kwargs):
        dados = {
            "descricao": descricao,
            "categoria": self.categoria,
            "competencia": date(2026, 3, 1),
            "valor": Decimal(valor),
            "data_vencimento": date(2026, 3, 10),
            "veiculo": self.veiculo,
            "manutencao": self.manutencao,
        }
        dados.update(kwargs)
        return ContaPagar.objects.create(**dados)

    def test_multiplas_contas_somam(self):
        self._conta("Peças", "500.00")
        self._conta("Mão de obra", "300.00")
        self._conta("Alinhamento", "100.00")
        self.assertEqual(self.manutencao.custo_financeiro(), Decimal("900.00"))

    def test_set_null_ao_remover_manutencao(self):
        conta = self._conta("Peças", "500.00")
        self.manutencao.delete()
        conta.refresh_from_db()
        self.assertIsNone(conta.manutencao_id)
        self.assertEqual(conta.veiculo_id, self.veiculo.pk)

    def test_categoria_exige_veiculo(self):
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        conta = ContaPagar(
            descricao="Gasolina",
            categoria=combustivel,
            competencia=date(2026, 3, 1),
            valor=Decimal("200.00"),
            data_vencimento=date(2026, 3, 10),
        )
        with self.assertRaises(ValidationError):
            conta.full_clean()

    def _instancia(self, **kwargs):
        dados = {
            "descricao": "Conta frota",
            "categoria": self.categoria,
            "competencia": date(2026, 3, 1),
            "valor": Decimal("100.00"),
            "data_vencimento": date(2026, 3, 10),
        }
        dados.update(kwargs)
        return ContaPagar(**dados)

    def test_manutencao_sem_veiculo(self):
        conta = self._instancia(manutencao=self.manutencao)
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("veiculo", contexto.exception.error_dict)

    def test_manutencao_com_veiculo_diferente(self):
        outro = criar_veiculo(placa="XYZ1A23")
        conta = self._instancia(manutencao=self.manutencao, veiculo=outro)
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("manutencao", contexto.exception.error_dict)

    def test_manutencao_com_veiculo_correto(self):
        conta = self._instancia(manutencao=self.manutencao, veiculo=self.veiculo)
        conta.full_clean()

    def test_obrigacao_sem_veiculo(self):
        obrigacao = ObrigacaoVeiculo.objects.create(
            veiculo=self.veiculo,
            tipo=ObrigacaoVeiculo.TIPO_IPVA,
            exercicio=2026,
        )
        conta = self._instancia(obrigacao=obrigacao)
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("veiculo", contexto.exception.error_dict)

    def test_obrigacao_com_veiculo_diferente(self):
        outro = criar_veiculo(placa="XYZ1A23")
        obrigacao = ObrigacaoVeiculo.objects.create(
            veiculo=self.veiculo,
            tipo=ObrigacaoVeiculo.TIPO_LICENCIAMENTO,
            exercicio=2026,
        )
        conta = self._instancia(obrigacao=obrigacao, veiculo=outro)
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("obrigacao", contexto.exception.error_dict)

    def test_obrigacao_com_veiculo_correto(self):
        obrigacao = ObrigacaoVeiculo.objects.create(
            veiculo=self.veiculo,
            tipo=ObrigacaoVeiculo.TIPO_SEGURO,
            exercicio=2026,
        )
        conta = self._instancia(obrigacao=obrigacao, veiculo=self.veiculo)
        conta.full_clean()

    def test_veiculo_sem_manutencao_obrigacao(self):
        conta = self._instancia(veiculo=self.veiculo)
        conta.full_clean()

    def test_manutencao_e_obrigacao_mesmo_veiculo(self):
        obrigacao = ObrigacaoVeiculo.objects.create(
            veiculo=self.veiculo,
            tipo=ObrigacaoVeiculo.TIPO_OUTRO,
            exercicio=2026,
        )
        conta = self._instancia(
            veiculo=self.veiculo,
            manutencao=self.manutencao,
            obrigacao=obrigacao,
        )
        conta.full_clean()

    def test_manutencao_e_obrigacao_veiculos_diferentes(self):
        outro = criar_veiculo(placa="XYZ1A23")
        obrigacao = ObrigacaoVeiculo.objects.create(
            veiculo=outro,
            tipo=ObrigacaoVeiculo.TIPO_IPVA,
            exercicio=2026,
        )
        conta = self._instancia(
            veiculo=self.veiculo,
            manutencao=self.manutencao,
            obrigacao=obrigacao,
        )
        with self.assertRaises(ValidationError) as contexto:
            conta.full_clean()
        self.assertIn("obrigacao", contexto.exception.error_dict)


class ContaPagarVinculoViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.veiculo = criar_veiculo()
        self.outro = criar_veiculo(placa="XYZ1A23")
        self.categoria = CategoriaFinanceira.objects.get(slug="manutencao")
        self.manutencao = ManutencaoVeiculo.objects.create(
            veiculo=self.veiculo,
            data_realizacao=date(2026, 3, 1),
            km_realizacao=51000,
            descricao="Revisão completa",
        )
        self.obrigacao = ObrigacaoVeiculo.objects.create(
            veiculo=self.veiculo,
            tipo=ObrigacaoVeiculo.TIPO_IPVA,
            exercicio=2026,
        )
        self.com_perm = User.objects.create_user(
            username="fin-cp-vinc",
            password="teste-123",
        )
        conceder_permissoes(
            self.com_perm,
            "financeiro.view_contapagar",
            "financeiro.add_contapagar",
            "financeiro.change_contapagar",
        )
        self.client.force_login(self.com_perm)

    def _payload(self, **kwargs):
        dados = {
            "descricao": "Peças da revisão",
            "categoria": self.categoria.pk,
            "competencia": "2026-03-01",
            "valor": "500.00",
            "data_vencimento": "2026-03-10",
            "status": ContaPagar.STATUS_PENDENTE,
            "observacoes": "",
        }
        dados.update(kwargs)
        return dados

    def test_post_manutencao_sem_veiculo(self):
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            self._payload(manutencao=self.manutencao.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContaPagar.objects.filter(descricao="Peças da revisão").exists())

    def test_post_manutencao_veiculo_incorreto(self):
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            self._payload(manutencao=self.manutencao.pk, veiculo=self.outro.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContaPagar.objects.filter(descricao="Peças da revisão").exists())

    def test_post_obrigacao_sem_veiculo(self):
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            self._payload(
                descricao="IPVA lançado",
                obrigacao=self.obrigacao.pk,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContaPagar.objects.filter(descricao="IPVA lançado").exists())

    def test_post_obrigacao_veiculo_incorreto(self):
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            self._payload(
                descricao="IPVA lançado",
                obrigacao=self.obrigacao.pk,
                veiculo=self.outro.pk,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContaPagar.objects.filter(descricao="IPVA lançado").exists())

    def test_post_manutencao_veiculo_correto(self):
        response = self.client.post(
            reverse("financeiro:cadastrar_conta_pagar"),
            self._payload(manutencao=self.manutencao.pk, veiculo=self.veiculo.pk),
        )
        self.assertEqual(response.status_code, 302)
        conta = ContaPagar.objects.get(descricao="Peças da revisão")
        self.assertEqual(conta.veiculo_id, self.veiculo.pk)
        self.assertEqual(conta.manutencao_id, self.manutencao.pk)

    def test_edicao_troca_veiculo_rejeitada(self):
        conta = ContaPagar.objects.create(
            descricao="Peças da revisão",
            categoria=self.categoria,
            competencia=date(2026, 3, 1),
            valor=Decimal("500.00"),
            data_vencimento=date(2026, 3, 10),
            veiculo=self.veiculo,
            manutencao=self.manutencao,
        )
        response = self.client.post(
            reverse("financeiro:editar_conta_pagar", args=[conta.pk]),
            self._payload(
                descricao="Peças da revisão",
                manutencao=self.manutencao.pk,
                veiculo=self.outro.pk,
            ),
        )
        self.assertEqual(response.status_code, 200)
        conta.refresh_from_db()
        self.assertEqual(conta.veiculo_id, self.veiculo.pk)


class IpvaTests(TestCase):
    def test_sp_2026_isento_ate_2005(self):
        veiculo = criar_veiculo(ano_fabricacao=2005, ano_modelo=2005)
        situacao = avaliar_ipva(veiculo, 2026)
        self.assertTrue(situacao.isento)
        self.assertFalse(situacao.aplicavel)
        self.assertTrue(situacao.determinado)
        self.assertEqual(situacao.situacao, SITUACAO_ISENTO)
        self.assertIn("2005", situacao.motivo)

    def test_sp_2026_anterior_a_2005_isento(self):
        veiculo = criar_veiculo(ano_fabricacao=2004, ano_modelo=2005)
        situacao = avaliar_ipva(veiculo, 2026)
        self.assertTrue(situacao.isento)
        self.assertEqual(situacao.situacao, SITUACAO_ISENTO)

    def test_sp_2026_devido_posterior(self):
        veiculo = criar_veiculo(ano_fabricacao=2006, ano_modelo=2006)
        situacao = avaliar_ipva(veiculo, 2026)
        self.assertFalse(situacao.isento)
        self.assertTrue(situacao.aplicavel)
        self.assertTrue(situacao.determinado)
        self.assertEqual(situacao.situacao, SITUACAO_DEVIDO)

    def test_sp_2026_sem_ano_nao_determinado(self):
        veiculo = criar_veiculo()
        veiculo.ano_fabricacao = None
        situacao = avaliar_ipva(veiculo, 2026)
        self.assertFalse(situacao.determinado)
        self.assertFalse(situacao.isento)
        self.assertFalse(situacao.aplicavel)
        self.assertEqual(situacao.situacao, SITUACAO_NAO_DETERMINADO)
        self.assertEqual(situacao.motivo, MOTIVO_ANO_AUSENTE)

    def test_outra_uf_nao_determinado(self):
        veiculo = criar_veiculo(uf="RJ")
        situacao = avaliar_ipva(veiculo, 2026)
        self.assertFalse(situacao.determinado)
        self.assertEqual(situacao.situacao, SITUACAO_NAO_DETERMINADO)

    def test_exercicio_sem_regra(self):
        veiculo = criar_veiculo(ano_fabricacao=2000, ano_modelo=2000)
        situacao = avaliar_ipva(veiculo, 2027)
        self.assertFalse(situacao.determinado)

    def test_regra_isolada_no_servico(self):
        self.assertIn(("SP", 2026), REGRAS_ISENCAO_IPVA)


class ObrigacoesTests(TestCase):
    def test_geracao_idempotente_e_licenciamento(self):
        veiculo = criar_veiculo(ano_fabricacao=2018)
        primeiro = gerar_obrigacoes_exercicio(veiculo, 2026)
        segundo = gerar_obrigacoes_exercicio(veiculo, 2026)
        self.assertEqual(primeiro.criadas, 2)
        self.assertEqual(segundo.criadas, 0)
        self.assertEqual(
            ObrigacaoVeiculo.objects.filter(veiculo=veiculo, exercicio=2026).count(),
            2,
        )
        ipva = ObrigacaoVeiculo.objects.get(
            veiculo=veiculo, tipo=ObrigacaoVeiculo.TIPO_IPVA, exercicio=2026
        )
        lic = ObrigacaoVeiculo.objects.get(
            veiculo=veiculo, tipo=ObrigacaoVeiculo.TIPO_LICENCIAMENTO, exercicio=2026
        )
        self.assertEqual(ipva.status, ObrigacaoVeiculo.STATUS_PENDENTE)
        self.assertEqual(lic.status, ObrigacaoVeiculo.STATUS_PENDENTE)
        self.assertFalse(
            ObrigacaoVeiculo.objects.filter(tipo=ObrigacaoVeiculo.TIPO_SEGURO).exists()
        )
        self.assertFalse(ContaPagar.objects.exists())

    def test_ipva_isento(self):
        veiculo = criar_veiculo(ano_fabricacao=2004, ano_modelo=2005)
        gerar_obrigacoes_exercicio(veiculo, 2026)
        ipva = ObrigacaoVeiculo.objects.get(tipo=ObrigacaoVeiculo.TIPO_IPVA)
        self.assertEqual(ipva.status, ObrigacaoVeiculo.STATUS_ISENTO)
        lic = ObrigacaoVeiculo.objects.get(tipo=ObrigacaoVeiculo.TIPO_LICENCIAMENTO)
        self.assertEqual(lic.status, ObrigacaoVeiculo.STATUS_PENDENTE)
        self.assertFalse(ContaPagar.objects.exists())

    def test_geracao_sem_ano_nao_cria_ipva_devido(self):
        veiculo = criar_veiculo()
        veiculo.ano_fabricacao = None
        primeiro = gerar_obrigacoes_exercicio(veiculo, 2026)
        self.assertIsNone(primeiro.ipva)
        self.assertFalse(
            ObrigacaoVeiculo.objects.filter(
                veiculo=veiculo,
                tipo=ObrigacaoVeiculo.TIPO_IPVA,
            ).exists()
        )
        self.assertEqual(
            ObrigacaoVeiculo.objects.filter(
                veiculo=veiculo,
                tipo=ObrigacaoVeiculo.TIPO_LICENCIAMENTO,
                exercicio=2026,
            ).count(),
            1,
        )
        self.assertFalse(ContaPagar.objects.exists())
        segundo = gerar_obrigacoes_exercicio(veiculo, 2026)
        self.assertEqual(segundo.criadas, 0)
        self.assertEqual(
            ObrigacaoVeiculo.objects.filter(veiculo=veiculo).count(),
            1,
        )
        self.assertFalse(ContaPagar.objects.exists())

    def test_gerar_frota_idempotente_dois_veiculos(self):
        ativo = criar_veiculo(placa="AAA1A11", ano_fabricacao=2018)
        inativo = criar_veiculo(placa="BBB1B11", ano_fabricacao=2010, ativo=False)
        primeiro = gerar_obrigacoes_frota(2026)
        self.assertGreaterEqual(primeiro.criadas, 2)
        self.assertFalse(
            ObrigacaoVeiculo.objects.filter(veiculo=inativo).exists()
        )
        self.assertEqual(
            ObrigacaoVeiculo.objects.filter(veiculo=ativo).count(),
            2,
        )
        segundo = gerar_obrigacoes_frota(2026)
        self.assertEqual(segundo.criadas, 0)
        self.assertFalse(ContaPagar.objects.exists())


class CategoriasVeiculoTests(TestCase):
    def test_categorias_especificas(self):
        ipva = CategoriaFinanceira.objects.get(slug="ipva")
        lic = CategoriaFinanceira.objects.get(slug="licenciamento")
        seguros = CategoriaFinanceira.objects.get(slug="seguros")
        combustivel = CategoriaFinanceira.objects.get(slug="combustivel")
        veiculos = CategoriaFinanceira.objects.get(slug="veiculos")
        manutencao = CategoriaFinanceira.objects.get(slug="manutencao")
        self.assertTrue(ipva.exige_veiculo)
        self.assertTrue(lic.exige_veiculo)
        self.assertTrue(seguros.exige_veiculo)
        self.assertTrue(combustivel.exige_veiculo)
        self.assertTrue(veiculos.exige_veiculo)
        self.assertFalse(manutencao.exige_veiculo)


class VeiculoUITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.com_perm = User.objects.create_user(
            username="fin-vei-ok", password="teste-123"
        )
        conceder_permissoes(
            self.com_perm,
            "financeiro.view_veiculo",
            "financeiro.add_veiculo",
            "financeiro.change_veiculo",
            "financeiro.view_planomanutencao",
            "financeiro.add_planomanutencao",
            "financeiro.change_planomanutencao",
            "financeiro.view_manutencaoveiculo",
            "financeiro.add_manutencaoveiculo",
            "financeiro.change_manutencaoveiculo",
            "financeiro.view_obrigacaoveiculo",
            "financeiro.add_obrigacaoveiculo",
            "financeiro.change_obrigacaoveiculo",
            "financeiro.view_contapagar",
        )
        self.sem_perm = User.objects.create_user(
            username="fin-vei-sem", password="teste-123"
        )
        self.veiculo = criar_veiculo()

    def test_lista_anonimo_redireciona(self):
        response = self.client.get(reverse("financeiro:lista_veiculos"))
        self.assertEqual(response.status_code, 302)

    def test_lista_sem_permissao_403(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(reverse("financeiro:lista_veiculos"))
        self.assertEqual(response.status_code, 403)

    def test_url_direta_sem_permissao(self):
        self.client.force_login(self.sem_perm)
        response = self.client.get(
            reverse("financeiro:detalhe_veiculo", args=[self.veiculo.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_cadastro_e_lista(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:cadastrar_veiculo"),
            {
                "marca": "VW",
                "modelo": "Saveiro",
                "versao": "",
                "placa": "RST1A23",
                "renavam": "123456789",
                "ano_fabricacao": "2015",
                "ano_modelo": "2016",
                "uf": "SP",
                "km_atual": "1000",
                "data_aquisicao": "",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Veiculo.objects.filter(placa="RST1A23").exists())
        lista = self.client.get(reverse("financeiro:lista_veiculos"))
        self.assertContains(lista, "Saveiro")
        self.assertContains(lista, "Veículos")

    def test_edicao_nao_reduz_km(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:editar_veiculo", args=[self.veiculo.pk]),
            {
                "marca": self.veiculo.marca,
                "modelo": self.veiculo.modelo,
                "versao": "",
                "placa": self.veiculo.placa,
                "renavam": "",
                "ano_fabricacao": str(self.veiculo.ano_fabricacao),
                "ano_modelo": str(self.veiculo.ano_modelo),
                "uf": self.veiculo.uf,
                "km_atual": "1000",
                "data_aquisicao": "",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.veiculo.refresh_from_db()
        self.assertEqual(self.veiculo.km_atual, 50000)

    def test_gerar_obrigacoes_nao_usa_get(self):
        self.client.force_login(self.com_perm)
        antes = ObrigacaoVeiculo.objects.count()
        self.client.get(reverse("financeiro:gerar_obrigacoes"))
        self.assertEqual(ObrigacaoVeiculo.objects.count(), antes)

    def test_gerar_obrigacoes_post(self):
        self.client.force_login(self.com_perm)
        response = self.client.post(
            reverse("financeiro:gerar_obrigacoes"),
            {"exercicio": "2026", "veiculo": str(self.veiculo.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ObrigacaoVeiculo.objects.filter(veiculo=self.veiculo, exercicio=2026).count(),
            2,
        )

    def test_download_anexo_protegido(self):
        arquivo = SimpleUploadedFile(
            "os.pdf", PDF_MINIMO, content_type="application/pdf"
        )
        manutencao = ManutencaoVeiculo.objects.create(
            veiculo=self.veiculo,
            data_realizacao=date(2026, 1, 10),
            km_realizacao=50100,
            descricao="OS",
            anexo=arquivo,
        )
        url = reverse(
            "financeiro:download_anexo_manutencao",
            args=[self.veiculo.pk, manutencao.pk],
        )
        self.client.force_login(self.sem_perm)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.com_perm)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")

    def test_dashboard_mostra_situacao_sem_hardcode_legal(self):
        self.client.force_login(self.com_perm)
        response = self.client.get(
            reverse("financeiro:detalhe_veiculo", args=[self.veiculo.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IPVA")
        self.assertNotContains(response, "REGRAS_ISENCAO_IPVA")
