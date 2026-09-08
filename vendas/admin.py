from django.contrib import admin

from core.auditoria import atribuir_criado_por
from estoque.services import registrar_saidas_venda

from .models import Venda, ItemVenda


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 1


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):

    inlines = [
        ItemVendaInline
    ]

    list_display = (
        'id',
        'cliente',
        'data',
        'criado_por',
        'quantidade_total',
        'mostrar_total'
    )

    list_filter = (
        'data',
        'criado_por',
    )

    readonly_fields = (
        'criado_por',
        'criado_em',
        'data',
    )

    def save_model(self, request, obj, form, change):
        if not change:
            atribuir_criado_por(obj, request.user)
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if change:
            return
        registrar_saidas_venda(form.instance)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("cliente")
            .prefetch_related("itens")
        )

    def quantidade_total(self, obj):
        return obj.quantidade_total

    quantidade_total.short_description = 'Qtd. Sacos'

    def mostrar_total(self, obj):
        return f'R$ {obj.total:.2f}'

    mostrar_total.short_description = 'Total'
