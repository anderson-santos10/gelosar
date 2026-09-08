from django.contrib import admin

from core.auditoria import atribuir_criado_por
from .models import Producao


@admin.register(Producao)
class ProducaoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "equipamento",
        "produto",
        "quantidade",
        "data_hora",
        "criado_por",
    )
    list_filter = (
        "data_hora",
        "criado_por",
    )
    readonly_fields = (
        "criado_por",
        "data_hora",
    )

    def save_model(self, request, obj, form, change):
        if not change:
            atribuir_criado_por(obj, request.user)
        super().save_model(request, obj, form, change)
