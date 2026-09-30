# Investimento fica para etapa posterior.
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from pathlib import Path
from uuid import uuid4

from django.utils.text import get_valid_filename, slugify

from core.cnpj import formatar_cnpj_cpf, normalizar_cnpj, validar_digitos_cpf_cnpj
from core.periodo import dia_local_atual
from equipamentos.validators import validar_arquivo_documento
from financeiro.placas import (
    UFS_BRASIL,
    formatar_placa,
    normalizar_placa,
    normalizar_renavam,
    placa_valida,
)


class Fornecedor(models.Model):
    nome = models.CharField(max_length=150)
    cnpj = models.CharField(max_length=18, blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=models.Q(cnpj__isnull=False),
                name="financeiro_fornecedor_cnpj_unico",
            ),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.cnpj = normalizar_cnpj(self.cnpj)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        try:
            self.cnpj = validar_digitos_cpf_cnpj(self.cnpj)
        except ValidationError as erro:
            raise ValidationError({"cnpj": erro.messages if hasattr(erro, "messages") else erro})

    @property
    def cnpj_formatado(self):
        return formatar_cnpj_cpf(self.cnpj)


class CategoriaFinanceira(models.Model):
    TIPO_DESPESA = "despesa"
    TIPO_INVESTIMENTO = "investimento"
    TIPO_RECEITA = "receita"
    TIPO_CHOICES = [
        (TIPO_DESPESA, "Despesa"),
        (TIPO_INVESTIMENTO, "Investimento"),
        (TIPO_RECEITA, "Receita"),
    ]

    nome = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default=TIPO_DESPESA,
    )
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveIntegerField(default=0)
    exige_veiculo = models.BooleanField(
        default=False,
        help_text="Se marcado, a ContaPagar desta categoria exige a seleção de um veículo.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Categoria financeira"
        verbose_name_plural = "Categorias financeiras"
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome, allow_unicode=False)
        super().save(*args, **kwargs)


class ContaRecorrente(models.Model):
    PERIODICIDADE_MENSAL = "mensal"
    PERIODICIDADE_CHOICES = [
        (PERIODICIDADE_MENSAL, "Mensal"),
    ]
    MENSAGEM_CATEGORIA_EXIGE_VEICULO = (
        "Categorias que exigem veículo não podem ser usadas em contas "
        "recorrentes. Cadastre esse lançamento pelo módulo de veículos ou "
        "como conta a pagar vinculada ao veículo."
    )

    descricao = models.CharField("Descrição", max_length=200)
    categoria = models.ForeignKey(
        CategoriaFinanceira,
        on_delete=models.PROTECT,
        related_name="contas_recorrentes",
        verbose_name="Categoria",
    )
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_recorrentes",
        verbose_name="Fornecedor",
    )
    valor = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(
                Decimal("0.01"),
                message="O valor deve ser maior que zero.",
            )
        ],
    )
    valor_estimado = models.BooleanField(
        "Valor estimado",
        default=False,
        help_text="Marque se o valor for uma estimativa e puder ser ajustado na conta gerada.",
    )
    periodicidade = models.CharField(
        "Periodicidade",
        max_length=20,
        choices=PERIODICIDADE_CHOICES,
        default=PERIODICIDADE_MENSAL,
    )
    dia_vencimento = models.PositiveSmallIntegerField(
        "Dia de vencimento",
        validators=[
            MinValueValidator(1, message="O dia de vencimento deve ser entre 1 e 28."),
            MaxValueValidator(28, message="O dia de vencimento deve ser entre 1 e 28."),
        ],
        help_text="Dia do mês (1 a 28) usado no vencimento das contas geradas.",
    )
    data_inicio = models.DateField("Data inicial")
    data_fim = models.DateField("Data final", null=True, blank=True)
    ativa = models.BooleanField(default=True)
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conta recorrente"
        verbose_name_plural = "Contas recorrentes"
        ordering = ["descricao"]

    def __str__(self):
        return self.descricao

    def clean(self):
        super().clean()
        erros = {}
        if self.valor is not None and self.valor <= 0:
            erros["valor"] = "O valor deve ser maior que zero."
        if self.dia_vencimento is not None and not (1 <= self.dia_vencimento <= 28):
            erros["dia_vencimento"] = "O dia de vencimento deve ser entre 1 e 28."
        if self.data_fim and self.data_inicio and self.data_fim < self.data_inicio:
            erros["data_fim"] = "A data final não pode ser anterior à data inicial."
        categoria = getattr(self, "categoria", None)
        if categoria and categoria.exige_veiculo:
            erros["categoria"] = self.MENSAGEM_CATEGORIA_EXIGE_VEICULO
        if erros:
            raise ValidationError(erros)


def _upload_financeiro(pasta, filename):
    extensao = Path(get_valid_filename(filename or "")).suffix.lower()
    return f"financeiro/{pasta}/{uuid4().hex}{extensao}"


def comprovante_conta_upload_to(instance, filename):
    return _upload_financeiro("comprovantes", filename)


class ContaPagar(models.Model):
    STATUS_PENDENTE = "pendente"
    STATUS_PAGO = "pago"
    STATUS_CANCELADO = "cancelado"
    STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente"),
        (STATUS_PAGO, "Pago"),
        (STATUS_CANCELADO, "Cancelado"),
    ]
    STATUS_FECHADOS = frozenset({STATUS_PAGO, STATUS_CANCELADO})
    MENSAGEM_LANCAMENTO_FECHADO = (
        "Conta paga ou cancelada não pode ser alterada."
    )

    FORMA_PIX = "pix"
    FORMA_BOLETO = "boleto"
    FORMA_TED = "ted"
    FORMA_DINHEIRO = "dinheiro"
    FORMA_CARTAO = "cartao"
    FORMA_OUTRO = "outro"
    FORMA_CHOICES = [
        (FORMA_PIX, "PIX"),
        (FORMA_BOLETO, "Boleto"),
        (FORMA_TED, "TED"),
        (FORMA_DINHEIRO, "Dinheiro"),
        (FORMA_CARTAO, "Cartão"),
        (FORMA_OUTRO, "Outro"),
    ]

    descricao = models.CharField("Descrição", max_length=200)
    categoria = models.ForeignKey(
        CategoriaFinanceira,
        on_delete=models.PROTECT,
        related_name="contas_pagar",
        verbose_name="Categoria",
    )
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_pagar",
        verbose_name="Fornecedor",
    )
    recorrente = models.ForeignKey(
        "ContaRecorrente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_geradas",
        verbose_name="Conta recorrente",
    )
    veiculo = models.ForeignKey(
        "Veiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_pagar",
        verbose_name="Veículo",
    )
    manutencao = models.ForeignKey(
        "ManutencaoVeiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_pagar",
        verbose_name="Manutenção",
    )
    obrigacao = models.ForeignKey(
        "ObrigacaoVeiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_pagar",
        verbose_name="Obrigação do veículo",
    )
    competencia = models.DateField(
        "Competência",
        help_text="Período da despesa (não confundir com o vencimento).",
    )
    valor = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(
                Decimal("0.01"),
                message="O valor deve ser maior que zero.",
            )
        ],
    )
    data_emissao = models.DateField("Data de emissão", null=True, blank=True)
    data_vencimento = models.DateField("Data de vencimento")
    data_pagamento = models.DateField("Data de pagamento", null=True, blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDENTE,
    )
    forma_pagamento = models.CharField(
        "Forma de pagamento",
        max_length=20,
        choices=FORMA_CHOICES,
        blank=True,
    )
    observacoes = models.TextField("Observações", blank=True)
    anexo = models.FileField(
        "Comprovante",
        upload_to=comprovante_conta_upload_to,
        blank=True,
        null=True,
        help_text="PDF, PNG, JPEG, DOCX ou XLSX.",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_pagar_criadas",
        editable=False,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conta a pagar"
        verbose_name_plural = "Contas a pagar"
        ordering = ["data_vencimento", "-id"]
        indexes = [
            models.Index(fields=["status", "data_vencimento"]),
            models.Index(fields=["categoria"]),
            models.Index(fields=["fornecedor"]),
            models.Index(fields=["competencia"]),
            models.Index(fields=["data_vencimento"]),
            models.Index(fields=["veiculo"]),
            models.Index(
                fields=["status", "data_pagamento"],
                name="financeiro_cp_status_pagto_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recorrente", "competencia"],
                condition=models.Q(recorrente__isnull=False),
                name="financeiro_contapagar_recorrente_competencia_unico",
            ),
        ]

    def __str__(self):
        return self.descricao

    @property
    def lancamento_fechado(self):
        return self.status in self.STATUS_FECHADOS

    def _status_persistido(self):
        if not self.pk:
            return None
        return (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
        )

    def _lancamento_persistido_foi_alterado(self):
        if not self.pk:
            return False
        original = (
            type(self)
            .objects.filter(pk=self.pk)
            .values(
                "descricao",
                "categoria_id",
                "fornecedor_id",
                "recorrente_id",
                "veiculo_id",
                "manutencao_id",
                "obrigacao_id",
                "competencia",
                "valor",
                "data_emissao",
                "data_vencimento",
                "data_pagamento",
                "status",
                "forma_pagamento",
                "observacoes",
                "anexo",
            )
            .first()
        )
        if not original or original["status"] not in self.STATUS_FECHADOS:
            return False
        campos = (
            "descricao",
            "categoria_id",
            "fornecedor_id",
            "recorrente_id",
            "veiculo_id",
            "manutencao_id",
            "obrigacao_id",
            "competencia",
            "valor",
            "data_emissao",
            "data_vencimento",
            "data_pagamento",
            "status",
            "forma_pagamento",
            "observacoes",
        )
        for campo in campos:
            if getattr(self, campo) != original[campo]:
                return True
        anexo_atual = self.anexo.name if self.anexo else ""
        anexo_original = original.get("anexo") or ""
        return anexo_atual != anexo_original

    def clean(self):
        super().clean()
        erros = {}
        if self._lancamento_persistido_foi_alterado():
            erros["__all__"] = self.MENSAGEM_LANCAMENTO_FECHADO
        if self.valor is not None and self.valor <= 0:
            erros["valor"] = "O valor deve ser maior que zero."

        if self.status == self.STATUS_PAGO and not self.data_pagamento:
            erros["data_pagamento"] = "Informe a data de pagamento para conta paga."

        if self.status == self.STATUS_PENDENTE and self.data_pagamento:
            erros["data_pagamento"] = "Conta pendente não deve ter data de pagamento."

        if self.data_pagamento and self.status != self.STATUS_PAGO:
            erros["status"] = "Com data de pagamento, o status deve ser Pago."

        if (
            self.data_pagamento
            and self.data_emissao
            and self.data_pagamento < self.data_emissao
        ):
            erros["data_pagamento"] = (
                "A data de pagamento não pode ser anterior à data de emissão."
            )

        if self.anexo:
            try:
                validar_arquivo_documento(self.anexo)
            except ValidationError as extra:
                erros["anexo"] = extra.messages if hasattr(extra, "messages") else extra

        categoria = getattr(self, "categoria", None)
        if categoria and categoria.exige_veiculo and not self.veiculo_id:
            erros["veiculo"] = "Esta categoria exige a seleção de um veículo."

        if self.manutencao_id:
            if not self.veiculo_id:
                erros["veiculo"] = "Informe o veículo vinculado à manutenção."
            elif self.manutencao.veiculo_id != self.veiculo_id:
                erros["manutencao"] = (
                    "A manutenção selecionada não pertence a este veículo."
                )

        if self.obrigacao_id:
            if not self.veiculo_id:
                erros.setdefault(
                    "veiculo",
                    "Informe o veículo vinculado à obrigação.",
                )
            elif self.obrigacao.veiculo_id != self.veiculo_id:
                erros["obrigacao"] = (
                    "A obrigação selecionada não pertence a este veículo."
                )

        if (
            self.manutencao_id
            and self.obrigacao_id
            and self.manutencao.veiculo_id != self.obrigacao.veiculo_id
        ):
            erros["obrigacao"] = (
                "A obrigação selecionada não pertence ao mesmo veículo da manutenção."
            )

        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        persistido = self._status_persistido()
        if persistido in self.STATUS_FECHADOS:
            raise ValidationError(
                {"__all__": [self.MENSAGEM_LANCAMENTO_FECHADO]}
            )
        super().save(*args, **kwargs)

    @property
    def vencida(self):
        if self.status != self.STATUS_PENDENTE or not self.data_vencimento:
            return False
        return self.data_vencimento < dia_local_atual()

    @property
    def status_display_financeiro(self):
        if self.vencida:
            return "Vencida"
        return self.get_status_display()


def anexo_manutencao_upload_to(instance, filename):
    return _upload_financeiro("manutencoes", filename)


class Veiculo(models.Model):
    marca = models.CharField("Marca", max_length=80)
    modelo = models.CharField("Modelo", max_length=80)
    versao = models.CharField("Versão", max_length=80, blank=True)
    placa = models.CharField("Placa", max_length=8, unique=True)
    renavam = models.CharField("RENAVAM", max_length=11, blank=True)
    ano_fabricacao = models.PositiveIntegerField("Ano de fabricação")
    ano_modelo = models.PositiveIntegerField("Ano modelo")
    uf = models.CharField(
        "UF",
        max_length=2,
        choices=UFS_BRASIL,
        default="SP",
    )
    km_atual = models.PositiveIntegerField("Km atual", default=0)
    data_aquisicao = models.DateField("Data de aquisição", null=True, blank=True)
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Veículo"
        verbose_name_plural = "Veículos"
        ordering = ["marca", "modelo", "placa"]

    def __str__(self):
        return f"{self.marca} {self.modelo} ({self.placa_formatada})"

    @property
    def placa_formatada(self):
        return formatar_placa(self.placa)

    def save(self, *args, **kwargs):
        self.placa = normalizar_placa(self.placa)
        self.renavam = normalizar_renavam(self.renavam)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        erros = {}
        placa = normalizar_placa(self.placa)
        if not placa_valida(placa):
            erros["placa"] = (
                "Informe uma placa válida no padrão antigo (ABC-1234) ou Mercosul (ABC1D23)."
            )
        ano_maximo = dia_local_atual().year + 1
        if self.ano_fabricacao and not (1950 <= self.ano_fabricacao <= ano_maximo):
            erros["ano_fabricacao"] = "Informe um ano de fabricação válido."
        if self.ano_modelo and not (1950 <= self.ano_modelo <= ano_maximo):
            erros["ano_modelo"] = "Informe um ano modelo válido."
        if (
            self.ano_fabricacao
            and self.ano_modelo
            and self.ano_modelo < self.ano_fabricacao
        ):
            erros["ano_modelo"] = (
                "O ano modelo não pode ser anterior ao ano de fabricação."
            )
        if self.renavam:
            digits = normalizar_renavam(self.renavam)
            if len(digits) not in (9, 11):
                erros["renavam"] = "Informe um RENAVAM com 9 ou 11 dígitos."
        if self.pk and self.km_atual is not None:
            km_persistido = (
                Veiculo.objects.filter(pk=self.pk)
                .values_list("km_atual", flat=True)
                .first()
            )
            if km_persistido is not None and self.km_atual < km_persistido:
                erros["km_atual"] = "A quilometragem atual não pode ser reduzida."
        if erros:
            raise ValidationError(erros)


class PlanoManutencao(models.Model):
    veiculo = models.ForeignKey(
        Veiculo,
        on_delete=models.PROTECT,
        related_name="planos",
        verbose_name="Veículo",
    )
    nome = models.CharField("Nome", max_length=120)
    descricao = models.TextField("Descrição", blank=True)
    intervalo_km = models.PositiveIntegerField(
        "Intervalo (km)",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    intervalo_meses = models.PositiveIntegerField(
        "Intervalo (meses)",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    antecedencia_alerta_km = models.PositiveIntegerField(
        "Alerta antecipado (km)",
        default=1000,
    )
    antecedencia_alerta_dias = models.PositiveIntegerField(
        "Alerta antecipado (dias)",
        default=30,
    )
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plano de manutenção"
        verbose_name_plural = "Planos de manutenção"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} — {self.veiculo}"

    def clean(self):
        super().clean()
        erros = {}
        if not self.intervalo_km and not self.intervalo_meses:
            mensagem = "Informe um intervalo em quilômetros, em meses, ou ambos."
            erros["intervalo_km"] = mensagem
            erros["intervalo_meses"] = mensagem
        if self.intervalo_km is not None and self.intervalo_km < 1:
            erros["intervalo_km"] = "O intervalo em km deve ser positivo."
        if self.intervalo_meses is not None and self.intervalo_meses < 1:
            erros["intervalo_meses"] = "O intervalo em meses deve ser positivo."
        if self.antecedencia_alerta_km is not None and self.antecedencia_alerta_km < 0:
            erros["antecedencia_alerta_km"] = "O alerta em km não pode ser negativo."
        if (
            self.antecedencia_alerta_dias is not None
            and self.antecedencia_alerta_dias < 0
        ):
            erros["antecedencia_alerta_dias"] = (
                "O alerta em dias não pode ser negativo."
            )
        if erros:
            raise ValidationError(erros)


class ManutencaoVeiculo(models.Model):
    veiculo = models.ForeignKey(
        Veiculo,
        on_delete=models.PROTECT,
        related_name="manutencoes",
        verbose_name="Veículo",
    )
    plano = models.ForeignKey(
        PlanoManutencao,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="historico",
        verbose_name="Plano",
    )
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manutencoes_veiculo",
        verbose_name="Fornecedor",
    )
    data_realizacao = models.DateField("Data de realização")
    km_realizacao = models.PositiveIntegerField("Km da realização")
    descricao = models.CharField("Descrição", max_length=200)
    observacoes = models.TextField("Observações", blank=True)
    anexo = models.FileField(
        "Anexo",
        upload_to=anexo_manutencao_upload_to,
        blank=True,
        null=True,
        help_text="PDF, PNG, JPEG, DOCX ou XLSX.",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manutencoes_veiculo_criadas",
        editable=False,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Manutenção de veículo"
        verbose_name_plural = "Manutenções de veículos"
        ordering = ["-data_realizacao", "-km_realizacao", "-id"]

    def __str__(self):
        return f"{self.descricao} ({self.veiculo.placa_formatada})"

    def clean(self):
        super().clean()
        erros = {}
        if self.km_realizacao is not None and self.km_realizacao < 0:
            erros["km_realizacao"] = "A quilometragem não pode ser negativa."
        if self.plano_id:
            plano_veiculo_id = getattr(self.plano, "veiculo_id", None)
            if plano_veiculo_id and self.veiculo_id and plano_veiculo_id != self.veiculo_id:
                erros["plano"] = "O plano selecionado não pertence a este veículo."
        if self.anexo:
            try:
                validar_arquivo_documento(self.anexo)
            except ValidationError as extra:
                erros["anexo"] = extra.messages if hasattr(extra, "messages") else extra
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.veiculo_id and self.km_realizacao is not None:
            km_atual = self.veiculo.km_atual or 0
            if self.km_realizacao > km_atual:
                Veiculo.objects.filter(pk=self.veiculo_id).update(
                    km_atual=self.km_realizacao
                )
                self.veiculo.km_atual = self.km_realizacao

    def custo_financeiro(self):
        zero = Decimal("0.00")
        total = self.contas_pagar.exclude(
            status=ContaPagar.STATUS_CANCELADO
        ).aggregate(total=models.Sum("valor"))["total"]
        return total if total is not None else zero


class ObrigacaoVeiculo(models.Model):
    TIPO_IPVA = "ipva"
    TIPO_LICENCIAMENTO = "licenciamento"
    TIPO_SEGURO = "seguro"
    TIPO_OUTRO = "outro"
    TIPO_CHOICES = [
        (TIPO_IPVA, "IPVA"),
        (TIPO_LICENCIAMENTO, "Licenciamento"),
        (TIPO_SEGURO, "Seguro"),
        (TIPO_OUTRO, "Outro"),
    ]

    STATUS_PENDENTE = "pendente"
    STATUS_PAGO = "pago"
    STATUS_ISENTO = "isento"
    STATUS_NAO_APLICAVEL = "nao_aplicavel"
    STATUS_CANCELADO = "cancelado"
    STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente"),
        (STATUS_PAGO, "Pago"),
        (STATUS_ISENTO, "Isento"),
        (STATUS_NAO_APLICAVEL, "Não aplicável"),
        (STATUS_CANCELADO, "Cancelado"),
    ]

    veiculo = models.ForeignKey(
        Veiculo,
        on_delete=models.PROTECT,
        related_name="obrigacoes",
        verbose_name="Veículo",
    )
    tipo = models.CharField("Tipo", max_length=20, choices=TIPO_CHOICES)
    exercicio = models.PositiveIntegerField("Exercício")
    data_vencimento = models.DateField("Data de vencimento", null=True, blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDENTE,
    )
    valor_previsto = models.DecimalField(
        "Valor previsto",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Obrigação de veículo"
        verbose_name_plural = "Obrigações de veículos"
        ordering = ["-exercicio", "tipo", "veiculo"]
        constraints = [
            models.UniqueConstraint(
                fields=["veiculo", "tipo", "exercicio"],
                name="financeiro_obrigacao_veiculo_tipo_exercicio_unico",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.exercicio} — {self.veiculo}"


class ContaReceber(models.Model):
    STATUS_PENDENTE = "pendente"
    STATUS_RECEBIDA = "recebida"
    STATUS_CANCELADA = "cancelada"
    STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente"),
        (STATUS_RECEBIDA, "Recebida"),
        (STATUS_CANCELADA, "Cancelada"),
    ]
    STATUS_FECHADOS = frozenset({STATUS_RECEBIDA, STATUS_CANCELADA})
    MENSAGEM_LANCAMENTO_FECHADO = (
        "Conta recebida ou cancelada não pode ser alterada."
    )
    MENSAGEM_CATEGORIA_TIPO = (
        "A categoria de uma conta a receber deve ser do tipo receita."
    )
    MENSAGEM_CLIENTE_VENDA = (
        "A venda selecionada não pertence a este cliente."
    )
    MENSAGEM_VALOR_VENDA = (
        "O valor deve coincidir com o total da venda."
    )

    FORMA_PIX = "pix"
    FORMA_DINHEIRO = "dinheiro"
    FORMA_CARTAO_CREDITO = "cartao_credito"
    FORMA_CARTAO_DEBITO = "cartao_debito"
    FORMA_TRANSFERENCIA = "transferencia"
    FORMA_BOLETO = "boleto"
    FORMA_CHEQUE = "cheque"
    FORMA_OUTRO = "outro"
    FORMA_CHOICES = [
        (FORMA_PIX, "PIX"),
        (FORMA_DINHEIRO, "Dinheiro"),
        (FORMA_CARTAO_CREDITO, "Cartão de crédito"),
        (FORMA_CARTAO_DEBITO, "Cartão de débito"),
        (FORMA_TRANSFERENCIA, "Transferência"),
        (FORMA_BOLETO, "Boleto"),
        (FORMA_CHEQUE, "Cheque"),
        (FORMA_OUTRO, "Outro"),
    ]

    descricao = models.CharField("Descrição", max_length=200)
    cliente = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.PROTECT,
        related_name="contas_receber",
        verbose_name="Cliente",
    )
    venda = models.OneToOneField(
        "vendas.Venda",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conta_receber",
        verbose_name="Venda",
    )
    categoria = models.ForeignKey(
        CategoriaFinanceira,
        on_delete=models.PROTECT,
        related_name="contas_receber",
        verbose_name="Categoria",
    )
    competencia = models.DateField(
        "Competência",
        help_text="Período da receita (não confundir com o vencimento).",
    )
    valor = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(
                Decimal("0.01"),
                message="O valor deve ser maior que zero.",
            )
        ],
    )
    data_emissao = models.DateField("Data de emissão", null=True, blank=True)
    data_vencimento = models.DateField("Data de vencimento")
    data_recebimento = models.DateField("Data de recebimento", null=True, blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDENTE,
    )
    forma_recebimento = models.CharField(
        "Forma de recebimento",
        max_length=20,
        choices=FORMA_CHOICES,
        blank=True,
    )
    observacoes = models.TextField("Observações", blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_receber_criadas",
        editable=False,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conta a receber"
        verbose_name_plural = "Contas a receber"
        ordering = ["data_vencimento", "-id"]
        indexes = [
            models.Index(fields=["status", "data_vencimento"]),
            models.Index(fields=["categoria"]),
            models.Index(fields=["cliente"]),
            models.Index(fields=["competencia"]),
            models.Index(fields=["data_vencimento"]),
        ]

    def __str__(self):
        return self.descricao

    @property
    def lancamento_fechado(self):
        return self.status in self.STATUS_FECHADOS

    def _status_persistido(self):
        if not self.pk:
            return None
        return (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
        )

    def _lancamento_persistido_foi_alterado(self):
        if not self.pk:
            return False
        original = (
            type(self)
            .objects.filter(pk=self.pk)
            .values(
                "descricao",
                "cliente_id",
                "venda_id",
                "categoria_id",
                "competencia",
                "valor",
                "data_emissao",
                "data_vencimento",
                "data_recebimento",
                "status",
                "forma_recebimento",
                "observacoes",
            )
            .first()
        )
        if not original or original["status"] not in self.STATUS_FECHADOS:
            return False
        for campo in original:
            if getattr(self, campo) != original[campo]:
                return True
        return False

    def _total_venda(self):
        if not self.venda_id:
            return None
        total = self.venda.total
        if total in (None, 0):
            return Decimal("0.00")
        return Decimal(str(total)).quantize(Decimal("0.01"))

    def clean(self):
        super().clean()
        erros = {}
        if self._lancamento_persistido_foi_alterado():
            erros["__all__"] = self.MENSAGEM_LANCAMENTO_FECHADO
        if self.valor is not None and self.valor <= 0:
            erros["valor"] = "O valor deve ser maior que zero."

        categoria = getattr(self, "categoria", None)
        if categoria and categoria.tipo != CategoriaFinanceira.TIPO_RECEITA:
            erros["categoria"] = self.MENSAGEM_CATEGORIA_TIPO

        if self.status == self.STATUS_RECEBIDA and not self.data_recebimento:
            erros["data_recebimento"] = (
                "Informe a data de recebimento para conta recebida."
            )
        if self.status == self.STATUS_PENDENTE and self.data_recebimento:
            erros["data_recebimento"] = (
                "Conta pendente não deve ter data de recebimento."
            )
        if self.status == self.STATUS_CANCELADA and self.data_recebimento:
            erros["data_recebimento"] = (
                "Conta cancelada não deve ter data de recebimento."
            )
        if self.data_recebimento and self.status != self.STATUS_RECEBIDA:
            erros["status"] = "Com data de recebimento, o status deve ser Recebida."
        if (
            self.data_recebimento
            and self.data_emissao
            and self.data_recebimento < self.data_emissao
        ):
            erros["data_recebimento"] = (
                "A data de recebimento não pode ser anterior à data de emissão."
            )

        venda = getattr(self, "venda", None)
        if venda:
            if self.cliente_id and venda.cliente_id != self.cliente_id:
                erros["venda"] = self.MENSAGEM_CLIENTE_VENDA
            total = self._total_venda()
            if total is not None and total <= 0:
                erros.setdefault(
                    "venda",
                    "A venda vinculada não possui total para gerar recebimento.",
                )
            elif (
                self.valor is not None
                and total is not None
                and self.valor.quantize(Decimal("0.01")) != total
            ):
                erros["valor"] = self.MENSAGEM_VALOR_VENDA

        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        persistido = self._status_persistido()
        if persistido in self.STATUS_FECHADOS:
            raise ValidationError(
                {"__all__": [self.MENSAGEM_LANCAMENTO_FECHADO]}
            )
        super().save(*args, **kwargs)

    @property
    def vencida(self):
        if self.status != self.STATUS_PENDENTE or not self.data_vencimento:
            return False
        return self.data_vencimento < dia_local_atual()

    @property
    def status_display_financeiro(self):
        if self.vencida:
            return "Vencida"
        return self.get_status_display()
