from django.contrib import admin

from .models import ItemPedido, ItemVenda, Pedido, Venda


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    fields = ("produto", "quantidade", "preco_unitario")
    readonly_fields = ("produto", "quantidade", "preco_unitario")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    inlines = [ItemPedidoInline]
    list_display = (
        "id",
        "cliente",
        "status",
        "cidade",
        "criado_em",
        "criado_por",
        "entregue_em",
        "entregue_por",
        "venda",
    )
    list_filter = ("status",)
    search_fields = ("cliente__nome", "endereco", "cidade", "observacoes")
    readonly_fields = (
        "cliente",
        "status",
        "endereco",
        "cidade",
        "observacoes",
        "criado_em",
        "criado_por",
        "entregue_em",
        "entregue_por",
        "venda",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("cliente", "criado_por", "entregue_por", "venda")
        )
