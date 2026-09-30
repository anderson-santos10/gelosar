from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):

    list_display = (
        'nome',
        'cnpj_formatado',
        'telefone',
        'cidade',
        'possui_equipamento_comodato',
        'ativo',
        'dashboard_link',
    )


    search_fields = (
        'nome',
        'cnpj',
        'telefone',
    )


    list_filter = (
        'ativo',
        'possui_equipamento_comodato',
        'cidade',
    )

    @admin.display(description="CNPJ / CPF", ordering="cnpj")
    def cnpj_formatado(self, obj):
        return obj.cnpj_formatado or "-"


    def dashboard_link(self, obj):

        url = reverse(
            'clientes:dashboard_cliente',
            args=[obj.pk]
        )

        return format_html(
            '<a class="button" href="{}">📊 Dashboard</a>',
            url
        )


    dashboard_link.short_description = 'Ações'
