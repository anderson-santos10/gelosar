from django.contrib import admin
from django.contrib.auth import get_permission_codename

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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        """Consulta segue view ou change. A gravação continua bloqueada."""
        opts = self.opts
        view_perm = f"{opts.app_label}.{get_permission_codename('view', opts)}"
        change_perm = f"{opts.app_label}.{get_permission_codename('change', opts)}"
        return request.user.has_perm(view_perm) or request.user.has_perm(
            change_perm
        )
