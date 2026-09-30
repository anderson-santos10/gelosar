from django.contrib import admin

from .forms import FornecedorForm
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


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    form = FornecedorForm
    list_display = (
        "nome",
        "cnpj_formatado",
        "telefone",
        "email",
        "ativo",
        "criado_em",
    )
    list_filter = ("ativo",)
    search_fields = ("nome", "cnpj", "telefone", "email")
    readonly_fields = ("criado_em", "atualizado_em")

    @admin.display(description="CNPJ / CPF", ordering="cnpj")
    def cnpj_formatado(self, obj):
        return obj.cnpj_formatado or "-"


@admin.register(CategoriaFinanceira)
class CategoriaFinanceiraAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "slug",
        "tipo",
        "ativo",
        "ordem",
        "exige_veiculo",
    )
    list_filter = ("tipo", "ativo", "exige_veiculo")
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}
    list_editable = ("ordem", "ativo")
    ordering = ("ordem", "nome")


@admin.register(ContaPagar)
class ContaPagarAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "fornecedor",
        "categoria",
        "veiculo",
        "valor",
        "data_vencimento",
        "status",
        "data_pagamento",
    )
    list_filter = ("status", "categoria", "forma_pagamento")
    search_fields = ("descricao", "fornecedor__nome", "observacoes")
    date_hierarchy = "data_vencimento"
    autocomplete_fields = (
        "fornecedor",
        "categoria",
        "recorrente",
        "veiculo",
        "manutencao",
        "obrigacao",
    )
    readonly_fields = ("criado_por", "criado_em", "atualizado_em")
    ordering = ("data_vencimento", "-id")

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is not None and obj.lancamento_fechado:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is not None and obj.lancamento_fechado:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        campos = list(self.readonly_fields)
        if obj is not None and obj.lancamento_fechado:
            for campo in obj._meta.fields:
                if campo.name not in campos and not campo.primary_key:
                    campos.append(campo.name)
        return campos


@admin.register(ContaReceber)
class ContaReceberAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "cliente",
        "venda",
        "categoria",
        "valor",
        "competencia",
        "data_vencimento",
        "status",
        "data_recebimento",
        "forma_recebimento",
    )
    list_filter = (
        "status",
        "categoria",
        "cliente",
        "forma_recebimento",
    )
    search_fields = ("descricao", "cliente__nome", "observacoes")
    date_hierarchy = "data_vencimento"
    autocomplete_fields = ("cliente", "categoria")
    raw_id_fields = ("venda",)
    readonly_fields = ("criado_por", "criado_em", "atualizado_em")
    ordering = ("data_vencimento", "-id")

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is not None and obj.lancamento_fechado:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is not None and obj.lancamento_fechado:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        campos = list(self.readonly_fields)
        if obj is not None and obj.lancamento_fechado:
            for campo in obj._meta.fields:
                if campo.name not in campos and not campo.primary_key:
                    campos.append(campo.name)
        return campos


@admin.register(ContaRecorrente)
class ContaRecorrenteAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "fornecedor",
        "categoria",
        "valor",
        "periodicidade",
        "dia_vencimento",
        "ativa",
    )
    list_filter = ("ativa", "periodicidade", "valor_estimado", "categoria")
    search_fields = ("descricao", "fornecedor__nome")
    autocomplete_fields = ("fornecedor", "categoria")
    readonly_fields = ("criado_em", "atualizado_em")


@admin.register(Veiculo)
class VeiculoAdmin(admin.ModelAdmin):
    list_display = (
        "placa",
        "marca",
        "modelo",
        "ano_modelo",
        "uf",
        "km_atual",
        "ativo",
    )
    list_filter = ("ativo", "uf", "marca")
    search_fields = ("placa", "marca", "modelo", "renavam")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("marca", "modelo", "placa")


@admin.register(PlanoManutencao)
class PlanoManutencaoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "veiculo",
        "intervalo_km",
        "intervalo_meses",
        "ativo",
    )
    list_filter = ("ativo",)
    search_fields = ("nome", "veiculo__placa", "veiculo__modelo")
    autocomplete_fields = ("veiculo",)
    readonly_fields = ("criado_em", "atualizado_em")


@admin.register(ManutencaoVeiculo)
class ManutencaoVeiculoAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "veiculo",
        "plano",
        "data_realizacao",
        "km_realizacao",
        "fornecedor",
    )
    list_filter = ("data_realizacao",)
    search_fields = ("descricao", "veiculo__placa", "observacoes")
    autocomplete_fields = ("veiculo", "plano", "fornecedor")
    readonly_fields = ("criado_por", "criado_em", "atualizado_em")
    date_hierarchy = "data_realizacao"


@admin.register(ObrigacaoVeiculo)
class ObrigacaoVeiculoAdmin(admin.ModelAdmin):
    list_display = (
        "tipo",
        "exercicio",
        "veiculo",
        "data_vencimento",
        "status",
        "valor_previsto",
    )
    list_filter = ("tipo", "status", "exercicio")
    search_fields = ("veiculo__placa", "observacoes")
    autocomplete_fields = ("veiculo",)
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-exercicio", "tipo")
