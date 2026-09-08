from django.contrib import admin

from .models import ContratoComodato, Equipamento


admin.site.register(Equipamento)


@admin.register(ContratoComodato)
class ContratoComodatoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_contrato",
        "cliente",
        "equipamento",
        "status",
        "data_inicio",
        "data_fim",
    )
    list_filter = (
        "status",
        "data_inicio",
    )
    search_fields = (
        "numero_contrato",
        "cliente__nome",
        "equipamento__nome",
    )
    readonly_fields = (
        "criado_em",
        "atualizado_em",
    )
    autocomplete_fields = ()
