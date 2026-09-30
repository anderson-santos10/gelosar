from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.text import slugify

from core.cnpj import (
    apenas_digitos,
    formatar_cnpj_cpf,
    validar_digitos_cpf_cnpj,
)
from equipamentos.validators import validar_arquivo_documento

from clientes.models import Cliente
from vendas.models import Venda

from financeiro.placas import normalizar_placa, placa_valida

from .models import (
    CategoriaFinanceira,
    ContaPagar,
    ContaReceber,
    ContaRecorrente,
    Fornecedor,
    ManutencaoVeiculo,
    ObrigacaoVeiculo,
    PlanoManutencao,
    Veiculo,
)


class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = [
            "nome",
            "cnpj",
            "telefone",
            "email",
            "observacoes",
            "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Ex.: João da Silva",
                }
            ),
            "cnpj": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "maxlength": "18",
                    "placeholder": "Ex.: 00.000.000/0000-00",
                }
            ),
            "telefone": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Ex.: (14) 99999-9999",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Ex.: contato@empresa.com.br",
                }
            ),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.cnpj and "cnpj" not in self.data:
            self.initial["cnpj"] = formatar_cnpj_cpf(self.instance.cnpj)

    def clean_cnpj(self):
        bruto = self.cleaned_data.get("cnpj")
        digitos = apenas_digitos(bruto)
        if not digitos:
            return None
        normalizado = validar_digitos_cpf_cnpj(bruto)
        duplicado = Fornecedor.objects.filter(cnpj=normalizado)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise ValidationError("Já existe um fornecedor com este CNPJ/CPF.")
        return normalizado


class CategoriaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = CategoriaFinanceira
        fields = [
            "nome",
            "slug",
            "tipo",
            "ordem",
            "exige_veiculo",
            "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "slug": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Gerado automaticamente se vazio",
                }
            ),
            "tipo": forms.Select(attrs={"class": "form-select gs-input"}),
            "ordem": forms.NumberInput(attrs={"class": "form-control gs-input", "min": 0}),
        }
        help_texts = {
            "slug": "Identificador interno único. Deixe em branco para gerar a partir do nome.",
            "exige_veiculo": "Marque se as contas desta categoria devem exigir um veículo.",
            "ordem": "Menor número aparece primeiro na listagem.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()
        nome = self.cleaned_data.get("nome") or self.instance.nome
        if not slug:
            slug = slugify(nome or "", allow_unicode=False)
        if not slug:
            raise ValidationError("Informe um slug ou um nome para gerá-lo.")
        duplicado = CategoriaFinanceira.objects.filter(slug=slug)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise ValidationError("Já existe uma categoria com este slug.")
        return slug


class ContaPagarForm(forms.ModelForm):
    class Meta:
        model = ContaPagar
        fields = [
            "descricao",
            "categoria",
            "fornecedor",
            "competencia",
            "valor",
            "data_emissao",
            "data_vencimento",
            "status",
            "data_pagamento",
            "forma_pagamento",
            "observacoes",
            "anexo",
            "veiculo",
            "manutencao",
            "obrigacao",
        ]
        widgets = {
            "descricao": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "categoria": forms.Select(attrs={"class": "form-select gs-input"}),
            "fornecedor": forms.Select(attrs={"class": "form-select gs-input"}),
            "competencia": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "valor": forms.NumberInput(
                attrs={
                    "class": "form-control gs-input",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "data_emissao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "data_vencimento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "status": forms.Select(attrs={"class": "form-select gs-input"}),
            "data_pagamento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "forma_pagamento": forms.Select(attrs={"class": "form-select gs-input"}),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
            "anexo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "veiculo": forms.Select(attrs={"class": "form-select gs-input"}),
            "manutencao": forms.Select(attrs={"class": "form-select gs-input"}),
            "obrigacao": forms.Select(attrs={"class": "form-select gs-input"}),
        }
        help_texts = {
            "competencia": "Período da despesa. Pode ser anterior ao vencimento.",
            "anexo": "PDF, PNG, JPEG, DOCX ou XLSX.",
            "data_pagamento": "Obrigatória se o status for Pago. Deixe vazia se Pendente.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorias = CategoriaFinanceira.objects.filter(
            ativo=True,
            tipo=CategoriaFinanceira.TIPO_DESPESA,
        )
        fornecedores = Fornecedor.objects.filter(ativo=True)
        if self.instance.pk:
            if self.instance.categoria_id:
                categorias = CategoriaFinanceira.objects.filter(
                    Q(ativo=True, tipo=CategoriaFinanceira.TIPO_DESPESA)
                    | Q(pk=self.instance.categoria_id)
                )
            if self.instance.fornecedor_id:
                fornecedores = Fornecedor.objects.filter(
                    Q(ativo=True) | Q(pk=self.instance.fornecedor_id)
                )
        self.fields["categoria"].queryset = categorias.order_by("ordem", "nome")
        self.fields["fornecedor"].queryset = fornecedores.order_by("nome")
        self.fields["fornecedor"].required = False
        self.fields["forma_pagamento"].required = False
        veiculos = Veiculo.objects.filter(ativo=True)
        if self.instance.pk and self.instance.veiculo_id:
            veiculos = Veiculo.objects.filter(
                Q(ativo=True) | Q(pk=self.instance.veiculo_id)
            )
        self.fields["veiculo"].queryset = veiculos.order_by("marca", "modelo")
        self.fields["veiculo"].required = False
        self.fields["manutencao"].queryset = ManutencaoVeiculo.objects.select_related(
            "veiculo"
        ).order_by("-data_realizacao")
        self.fields["manutencao"].required = False
        self.fields["obrigacao"].queryset = ObrigacaoVeiculo.objects.select_related(
            "veiculo"
        ).order_by("-exercicio")
        self.fields["obrigacao"].required = False
        self.exige_veiculo_ids = ",".join(
            str(pk)
            for pk in categorias.filter(exige_veiculo=True).values_list("pk", flat=True)
        )
        for nome in ("competencia", "data_emissao", "data_vencimento", "data_pagamento"):
            self.fields[nome].input_formats = ["%Y-%m-%d"]

    def clean(self):
        dados = super().clean()
        persistido = self.instance._status_persistido()
        if persistido in ContaPagar.STATUS_FECHADOS:
            raise ValidationError(ContaPagar.MENSAGEM_LANCAMENTO_FECHADO)
        veiculo = dados.get("veiculo")
        manutencao = dados.get("manutencao")
        obrigacao = dados.get("obrigacao")
        if manutencao and not veiculo:
            self.add_error(
                "veiculo",
                "Informe o veículo vinculado à manutenção.",
            )
        if obrigacao and not veiculo:
            self.add_error(
                "veiculo",
                "Informe o veículo vinculado à obrigação.",
            )
        if manutencao and veiculo and manutencao.veiculo_id != veiculo.pk:
            self.add_error(
                "manutencao",
                "A manutenção selecionada não pertence a este veículo.",
            )
        if obrigacao and veiculo and obrigacao.veiculo_id != veiculo.pk:
            self.add_error(
                "obrigacao",
                "A obrigação selecionada não pertence a este veículo.",
            )
        if (
            manutencao
            and obrigacao
            and manutencao.veiculo_id != obrigacao.veiculo_id
        ):
            self.add_error(
                "obrigacao",
                "A obrigação selecionada não pertence ao mesmo veículo da manutenção.",
            )
        return dados

    def clean_anexo(self):
        arquivo = self.cleaned_data.get("anexo")
        if arquivo:
            validar_arquivo_documento(arquivo)
        return arquivo

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        if valor is not None and valor <= 0:
            raise ValidationError("O valor deve ser maior que zero.")
        return valor


class ContaRecorrenteForm(forms.ModelForm):
    class Meta:
        model = ContaRecorrente
        fields = [
            "descricao",
            "categoria",
            "fornecedor",
            "valor",
            "valor_estimado",
            "periodicidade",
            "dia_vencimento",
            "data_inicio",
            "data_fim",
            "ativa",
            "observacoes",
        ]
        widgets = {
            "descricao": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "categoria": forms.Select(attrs={"class": "form-select gs-input"}),
            "fornecedor": forms.Select(attrs={"class": "form-select gs-input"}),
            "valor": forms.NumberInput(
                attrs={
                    "class": "form-control gs-input",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "periodicidade": forms.Select(attrs={"class": "form-select gs-input"}),
            "dia_vencimento": forms.NumberInput(
                attrs={"class": "form-control gs-input", "min": 1, "max": 28}
            ),
            "data_inicio": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "data_fim": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
        }
        help_texts = {
            "valor_estimado": "Marque se o valor for aproximado e puder ser ajustado na conta gerada.",
            "dia_vencimento": "Somente de 1 a 28, para evitar meses curtos.",
            "data_fim": "Opcional. Depois desta data a recorrência deixa de gerar contas.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorias = CategoriaFinanceira.objects.filter(
            ativo=True,
            tipo=CategoriaFinanceira.TIPO_DESPESA,
        )
        fornecedores = Fornecedor.objects.filter(ativo=True)
        if self.instance.pk:
            if self.instance.categoria_id:
                categorias = CategoriaFinanceira.objects.filter(
                    Q(ativo=True, tipo=CategoriaFinanceira.TIPO_DESPESA)
                    | Q(pk=self.instance.categoria_id)
                )
            if self.instance.fornecedor_id:
                fornecedores = Fornecedor.objects.filter(
                    Q(ativo=True) | Q(pk=self.instance.fornecedor_id)
                )
        self.fields["categoria"].queryset = categorias.order_by("ordem", "nome")
        self.fields["fornecedor"].queryset = fornecedores.order_by("nome")
        self.fields["fornecedor"].required = False
        for nome in ("data_inicio", "data_fim"):
            self.fields[nome].input_formats = ["%Y-%m-%d"]

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        if valor is not None and valor <= 0:
            raise ValidationError("O valor deve ser maior que zero.")
        return valor

    def clean_dia_vencimento(self):
        dia = self.cleaned_data.get("dia_vencimento")
        if dia is not None and not (1 <= dia <= 28):
            raise ValidationError("O dia de vencimento deve ser entre 1 e 28.")
        return dia

    def clean_categoria(self):
        categoria = self.cleaned_data.get("categoria")
        if categoria and categoria.exige_veiculo:
            raise ValidationError(ContaRecorrente.MENSAGEM_CATEGORIA_EXIGE_VEICULO)
        return categoria

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio")
        fim = dados.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim", "A data final não pode ser anterior à data inicial.")
        return dados


MESES_CHOICES = [
    (1, "Janeiro"),
    (2, "Fevereiro"),
    (3, "Março"),
    (4, "Abril"),
    (5, "Maio"),
    (6, "Junho"),
    (7, "Julho"),
    (8, "Agosto"),
    (9, "Setembro"),
    (10, "Outubro"),
    (11, "Novembro"),
    (12, "Dezembro"),
]


class GerarCompetenciaForm(forms.Form):
    mes = forms.TypedChoiceField(
        label="Mês",
        choices=MESES_CHOICES,
        coerce=int,
        widget=forms.Select(attrs={"class": "form-select gs-input"}),
    )
    ano = forms.IntegerField(
        label="Ano",
        min_value=2000,
        max_value=2100,
        widget=forms.NumberInput(attrs={"class": "form-control gs-input"}),
    )


class VeiculoForm(forms.ModelForm):
    class Meta:
        model = Veiculo
        fields = [
            "marca",
            "modelo",
            "versao",
            "placa",
            "renavam",
            "ano_fabricacao",
            "ano_modelo",
            "uf",
            "km_atual",
            "data_aquisicao",
            "ativo",
            "observacoes",
        ]
        widgets = {
            "marca": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "modelo": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "versao": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "placa": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "ABC1D23",
                    "autocomplete": "off",
                }
            ),
            "renavam": forms.TextInput(
                attrs={"class": "form-control gs-input", "inputmode": "numeric"}
            ),
            "ano_fabricacao": forms.NumberInput(attrs={"class": "form-control gs-input"}),
            "ano_modelo": forms.NumberInput(attrs={"class": "form-control gs-input"}),
            "uf": forms.Select(attrs={"class": "form-select gs-input"}),
            "km_atual": forms.NumberInput(
                attrs={"class": "form-control gs-input", "min": 0}
            ),
            "data_aquisicao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_aquisicao"].input_formats = ["%Y-%m-%d"]
        if self.instance.pk and self.instance.placa and "placa" not in self.data:
            self.initial["placa"] = self.instance.placa_formatada

    def clean_placa(self):
        placa = normalizar_placa(self.cleaned_data.get("placa"))
        if not placa_valida(placa):
            raise ValidationError(
                "Informe uma placa válida no padrão antigo (ABC-1234) ou Mercosul (ABC1D23)."
            )
        duplicado = Veiculo.objects.filter(placa=placa)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise ValidationError("Já existe um veículo com esta placa.")
        return placa

    def clean_km_atual(self):
        km = self.cleaned_data.get("km_atual")
        if (
            self.instance.pk
            and km is not None
            and self.instance.km_atual is not None
            and km < self.instance.km_atual
        ):
            raise ValidationError("A quilometragem atual não pode ser reduzida.")
        return km


class PlanoManutencaoForm(forms.ModelForm):
    class Meta:
        model = PlanoManutencao
        fields = [
            "nome",
            "descricao",
            "intervalo_km",
            "intervalo_meses",
            "antecedencia_alerta_km",
            "antecedencia_alerta_dias",
            "ativo",
            "observacoes",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "descricao": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
            "intervalo_km": forms.NumberInput(
                attrs={"class": "form-control gs-input", "min": 1}
            ),
            "intervalo_meses": forms.NumberInput(
                attrs={"class": "form-control gs-input", "min": 1}
            ),
            "antecedencia_alerta_km": forms.NumberInput(
                attrs={"class": "form-control gs-input", "min": 0}
            ),
            "antecedencia_alerta_dias": forms.NumberInput(
                attrs={"class": "form-control gs-input", "min": 0}
            ),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
        }
        help_texts = {
            "intervalo_km": "Opcional se houver intervalo em meses. Use ambos para o que ocorrer primeiro.",
            "intervalo_meses": "Opcional se houver intervalo em km.",
        }


class ManutencaoVeiculoForm(forms.ModelForm):
    class Meta:
        model = ManutencaoVeiculo
        fields = [
            "plano",
            "fornecedor",
            "data_realizacao",
            "km_realizacao",
            "descricao",
            "observacoes",
            "anexo",
        ]
        widgets = {
            "plano": forms.Select(attrs={"class": "form-select gs-input"}),
            "fornecedor": forms.Select(attrs={"class": "form-select gs-input"}),
            "data_realizacao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "km_realizacao": forms.NumberInput(
                attrs={"class": "form-control gs-input", "min": 0}
            ),
            "descricao": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
            "anexo": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.veiculo = kwargs.pop("veiculo")
        super().__init__(*args, **kwargs)
        self.fields["data_realizacao"].input_formats = ["%Y-%m-%d"]
        planos = PlanoManutencao.objects.filter(veiculo=self.veiculo, ativo=True)
        if self.instance.pk and self.instance.plano_id:
            planos = PlanoManutencao.objects.filter(
                Q(veiculo=self.veiculo, ativo=True) | Q(pk=self.instance.plano_id)
            )
        self.fields["plano"].queryset = planos.order_by("nome")
        self.fields["plano"].required = False
        fornecedores = Fornecedor.objects.filter(ativo=True)
        if self.instance.pk and self.instance.fornecedor_id:
            fornecedores = Fornecedor.objects.filter(
                Q(ativo=True) | Q(pk=self.instance.fornecedor_id)
            )
        self.fields["fornecedor"].queryset = fornecedores.order_by("nome")
        self.fields["fornecedor"].required = False
        if not self.instance.pk and not self.initial.get("km_realizacao"):
            self.initial["km_realizacao"] = self.veiculo.km_atual

    def clean_anexo(self):
        arquivo = self.cleaned_data.get("anexo")
        if arquivo:
            validar_arquivo_documento(arquivo)
        return arquivo

    def clean(self):
        dados = super().clean()
        plano = dados.get("plano")
        if plano and plano.veiculo_id != self.veiculo.pk:
            self.add_error("plano", "O plano selecionado não pertence a este veículo.")
        return dados


class ObrigacaoVeiculoForm(forms.ModelForm):
    class Meta:
        model = ObrigacaoVeiculo
        fields = [
            "tipo",
            "exercicio",
            "data_vencimento",
            "status",
            "valor_previsto",
            "observacoes",
        ]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select gs-input"}),
            "exercicio": forms.NumberInput(attrs={"class": "form-control gs-input"}),
            "data_vencimento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "status": forms.Select(attrs={"class": "form-select gs-input"}),
            "valor_previsto": forms.NumberInput(
                attrs={
                    "class": "form-control gs-input",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.veiculo = kwargs.pop("veiculo", None)
        super().__init__(*args, **kwargs)
        self.fields["data_vencimento"].input_formats = ["%Y-%m-%d"]
        if self.instance.pk:
            self.fields["tipo"].disabled = True
            self.fields["exercicio"].disabled = True

    def clean_valor_previsto(self):
        valor = self.cleaned_data.get("valor_previsto")
        if valor is not None and valor < 0:
            raise ValidationError("O valor previsto não pode ser negativo.")
        return valor


class GerarObrigacoesForm(forms.Form):
    exercicio = forms.IntegerField(
        label="Exercício",
        min_value=2000,
        max_value=2100,
        widget=forms.NumberInput(attrs={"class": "form-control gs-input"}),
    )
    veiculo = forms.ModelChoiceField(
        label="Veículo",
        queryset=Veiculo.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select gs-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["veiculo"].queryset = Veiculo.objects.filter(ativo=True).order_by(
            "marca", "modelo"
        )
        self.fields["veiculo"].empty_label = "Todos os veículos ativos"


class ContaReceberForm(forms.ModelForm):
    class Meta:
        model = ContaReceber
        fields = [
            "descricao",
            "cliente",
            "venda",
            "categoria",
            "competencia",
            "valor",
            "data_emissao",
            "data_vencimento",
            "status",
            "data_recebimento",
            "forma_recebimento",
            "observacoes",
        ]
        widgets = {
            "descricao": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "cliente": forms.Select(attrs={"class": "form-select gs-input"}),
            "venda": forms.Select(attrs={"class": "form-select gs-input"}),
            "categoria": forms.Select(attrs={"class": "form-select gs-input"}),
            "competencia": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "valor": forms.NumberInput(
                attrs={
                    "class": "form-control gs-input",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "data_emissao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "data_vencimento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "status": forms.Select(attrs={"class": "form-select gs-input"}),
            "data_recebimento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"},
            ),
            "forma_recebimento": forms.Select(attrs={"class": "form-select gs-input"}),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 3}
            ),
        }
        help_texts = {
            "competencia": "Período da receita. Pode ser anterior ao vencimento.",
            "venda": "Opcional. Uma venda só pode ter uma conta a receber.",
            "data_recebimento": "Obrigatória se o status for Recebida. Deixe vazia se Pendente.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorias = CategoriaFinanceira.objects.filter(
            ativo=True,
            tipo=CategoriaFinanceira.TIPO_RECEITA,
        )
        clientes = Cliente.objects.filter(ativo=True)
        vendas = Venda.objects.select_related("cliente").filter(
            conta_receber__isnull=True
        )
        if self.instance.pk:
            if self.instance.categoria_id:
                categorias = CategoriaFinanceira.objects.filter(
                    Q(ativo=True, tipo=CategoriaFinanceira.TIPO_RECEITA)
                    | Q(pk=self.instance.categoria_id)
                )
            if self.instance.cliente_id:
                clientes = Cliente.objects.filter(
                    Q(ativo=True) | Q(pk=self.instance.cliente_id)
                )
            if self.instance.venda_id:
                vendas = Venda.objects.select_related("cliente").filter(
                    Q(pk=self.instance.venda_id) | Q(conta_receber__isnull=True)
                )
        self.fields["categoria"].queryset = categorias.order_by("ordem", "nome")
        self.fields["cliente"].queryset = clientes.order_by("nome")
        self.fields["venda"].queryset = vendas.order_by("-id")
        self.fields["venda"].required = False
        self.fields["forma_recebimento"].required = False
        for nome in (
            "competencia",
            "data_emissao",
            "data_vencimento",
            "data_recebimento",
        ):
            self.fields[nome].input_formats = ["%Y-%m-%d"]

    def clean_categoria(self):
        categoria = self.cleaned_data.get("categoria")
        if categoria and categoria.tipo != CategoriaFinanceira.TIPO_RECEITA:
            raise ValidationError(ContaReceber.MENSAGEM_CATEGORIA_TIPO)
        return categoria

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        if valor is not None and valor <= 0:
            raise ValidationError("O valor deve ser maior que zero.")
        return valor

    def clean(self):
        dados = super().clean()
        persistido = self.instance._status_persistido()
        if persistido in ContaReceber.STATUS_FECHADOS:
            raise ValidationError(ContaReceber.MENSAGEM_LANCAMENTO_FECHADO)
        cliente = dados.get("cliente")
        venda = dados.get("venda")
        if venda and cliente and venda.cliente_id != cliente.pk:
            self.add_error("venda", ContaReceber.MENSAGEM_CLIENTE_VENDA)
        return dados
