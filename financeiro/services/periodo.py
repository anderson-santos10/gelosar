from calendar import monthrange
from datetime import date, timedelta

from core.periodo import dia_local_atual

PERIODO_ESTE_MES = "este_mes"
PERIODO_MES_ANTERIOR = "mes_anterior"
PERIODO_ULTIMOS_3 = "ultimos_3"
PERIODO_ULTIMOS_6 = "ultimos_6"
PERIODO_ESTE_ANO = "este_ano"
PERIODO_PERSONALIZADO = "personalizado"

PERIODO_OPCOES = [
    (PERIODO_ESTE_MES, "Este mês"),
    (PERIODO_MES_ANTERIOR, "Mês anterior"),
    (PERIODO_ULTIMOS_3, "Últimos 3 meses"),
    (PERIODO_ULTIMOS_6, "Últimos 6 meses"),
    (PERIODO_ESTE_ANO, "Este ano"),
    (PERIODO_PERSONALIZADO, "Personalizado"),
]

# Gráficos de evolução: diário até este limite (inclusive); acima, mensal.
LIMITE_DIAS_AGRUPAMENTO_DIARIO = 45


def parse_date(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def ultimo_dia_mes(ano, mes):
    return date(ano, mes, monthrange(ano, mes)[1])


def deslocar_meses(referencia, meses):
    indice = referencia.year * 12 + (referencia.month - 1) + meses
    ano = indice // 12
    mes = indice % 12 + 1
    dia = min(referencia.day, monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def mes_calendario(referencia):
    inicio = date(referencia.year, referencia.month, 1)
    return inicio, ultimo_dia_mes(referencia.year, referencia.month)


def resolver_periodo(params, hoje=None):
    hoje = hoje or dia_local_atual()
    inicio_param = parse_date(params.get("inicio"))
    fim_param = parse_date(params.get("fim"))
    chave = (params.get("periodo") or "").strip()

    if inicio_param and fim_param:
        if fim_param < inicio_param:
            inicio_param, fim_param = fim_param, inicio_param
        if not chave:
            chave = PERIODO_PERSONALIZADO
        if chave == PERIODO_PERSONALIZADO:
            return chave, inicio_param, fim_param

    if chave not in {item[0] for item in PERIODO_OPCOES}:
        chave = PERIODO_ESTE_MES

    if chave == PERIODO_MES_ANTERIOR:
        ref = deslocar_meses(date(hoje.year, hoje.month, 1), -1)
        inicio, fim = mes_calendario(ref)
    elif chave == PERIODO_ULTIMOS_3:
        fim = hoje
        inicio = deslocar_meses(date(hoje.year, hoje.month, 1), -2)
    elif chave == PERIODO_ULTIMOS_6:
        fim = hoje
        inicio = deslocar_meses(date(hoje.year, hoje.month, 1), -5)
    elif chave == PERIODO_ESTE_ANO:
        inicio = date(hoje.year, 1, 1)
        fim = hoje
    else:
        chave = PERIODO_ESTE_MES
        inicio, fim = mes_calendario(hoje)
    return chave, inicio, fim


def periodo_anterior_equivalente(chave, inicio, fim):
    if chave == PERIODO_ESTE_MES:
        ref = deslocar_meses(inicio, -1)
        return mes_calendario(ref)
    if chave == PERIODO_MES_ANTERIOR:
        ref = deslocar_meses(inicio, -1)
        return mes_calendario(ref)
    if chave == PERIODO_ULTIMOS_3:
        anterior_fim = inicio - timedelta(days=1)
        anterior_inicio = deslocar_meses(date(inicio.year, inicio.month, 1), -3)
        return anterior_inicio, anterior_fim
    if chave == PERIODO_ULTIMOS_6:
        anterior_fim = inicio - timedelta(days=1)
        anterior_inicio = deslocar_meses(date(inicio.year, inicio.month, 1), -6)
        return anterior_inicio, anterior_fim
    if chave == PERIODO_ESTE_ANO:
        return date(inicio.year - 1, 1, 1), date(inicio.year - 1, 12, 31)
    delta = (fim - inicio).days + 1
    anterior_fim = inicio - timedelta(days=1)
    anterior_inicio = anterior_fim - timedelta(days=delta - 1)
    return anterior_inicio, anterior_fim
