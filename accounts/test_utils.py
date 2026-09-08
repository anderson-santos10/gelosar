from django.contrib.auth.models import Permission


def conceder_permissoes(user, *permissoes):
    """Concede permissões nativas. Formato: 'app_label.codename'."""

    for permissao in permissoes:
        app_label, codename = permissao.split(".", 1)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            )
        )
