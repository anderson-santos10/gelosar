from datetime import date

from django.core.exceptions import ImproperlyConfigured


def parse_data_corte(value):
    """
    Interpreta DJANGO_ESTOQUE_DATA_CORTE.

    Ausente ou vazio → None (controle oficial não ativado).
    Formato válido → date (YYYY-MM-DD).
    Formato inválido → ImproperlyConfigured (não silenciar).
    """
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ImproperlyConfigured(
            "DJANGO_ESTOQUE_DATA_CORTE deve estar no formato YYYY-MM-DD. "
            f"Valor recebido: {raw!r}."
        )


def get_data_corte():
    """Data de corte configurada, ou None se o controle oficial não estiver ativo."""
    from django.conf import settings

    return getattr(settings, "ESTOQUE_DATA_CORTE", None)
