from django.contrib import admin
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
        'quantidade_total',
        'mostrar_total'
    )


    def quantidade_total(self, obj):
        return sum(
            item.quantidade
            for item in obj.itens.all()
        )


    quantidade_total.short_description = 'Qtd. Sacos'


    def mostrar_total(self, obj):
        return f'R$ {obj.total:.2f}'


    mostrar_total.short_description = 'Total'