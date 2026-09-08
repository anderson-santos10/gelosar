from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):

    list_display = (
        'nome',
        'cnpj',
        'telefone',
        'cidade',
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
        'cidade',
    )


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
