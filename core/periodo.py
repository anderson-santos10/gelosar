"""Limites de um dia civil no timezone ativo do Django (TIME_ZONE).

Não usar data_hora__date=... em DateTimeField com USE_TZ: o banco pode
converter em UTC e mudar o dia. Prefira [inicio, fim) timezone-aware.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone


def dia_local_atual():
    return timezone.localdate()


def intervalo_dia_local(dia=None):
    """Retorna (inicio inclusive, fim exclusivo) do dia no TZ corrente."""
    if dia is None:
        dia = timezone.localdate()
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(dia, time.min), tz)
    fim = inicio + timedelta(days=1)
    return inicio, fim
