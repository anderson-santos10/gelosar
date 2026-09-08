from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied


class ModulePermissionRequiredMixin(PermissionRequiredMixin):
    """Exige permissão nativa do Django.

    Anônimo: redireciona para o login (via AccessMixin).
    Autenticado sem permissão: HTTP 403.
    Superuser: has_perm() retorna True para qualquer permissão.
    """

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()


def module_permission_required(perm):
    """Equivalente FBV: login se anônimo; 403 se autenticado sem permissão."""

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.has_perm(perm):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
