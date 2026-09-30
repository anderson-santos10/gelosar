import calendar
from dataclasses import dataclass
from datetime import date

from core.periodo import dia_local_atual
from financeiro.models import ManutencaoVeiculo, PlanoManutencao

SITUACAO_EM_DIA = "em_dia"
SITUACAO_PROXIMA = "proxima"
SITUACAO_ATRASADA = "atrasada"
SITUACAO_SEM_HISTORICO = "sem_historico"
SITUACAO_INATIVO = "inativo"

SITUACAO_ROTULOS = {
    SITUACAO_EM_DIA: "EM DIA",
    SITUACAO_PROXIMA: "PRÓXIMA",
    SITUACAO_ATRASADA: "ATRASADA",
    SITUACAO_SEM_HISTORICO: "SEM HISTÓRICO",
    SITUACAO_INATIVO: "INATIVO",
}

SITUACAO_PRIORIDADE = {
    SITUACAO_ATRASADA: 4,
    SITUACAO_PROXIMA: 3,
    SITUACAO_SEM_HISTORICO: 2,
    SITUACAO_EM_DIA: 1,
    SITUACAO_INATIVO: 0,
}


def adicionar_meses(referencia, meses):
    mes_indice = referencia.month - 1 + int(meses)
    ano = referencia.year + mes_indice // 12
    mes = mes_indice % 12 + 1
    dia = min(referencia.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


@dataclass(frozen=True)
class SituacaoManutencao:
    plano: PlanoManutencao
    ultima: ManutencaoVeiculo | None
    proxima_km: int | None
    proxima_data: date | None
    km_restantes: int | None
    dias_restantes: int | None
    situacao: str

    @property
    def rotulo(self):
        return SITUACAO_ROTULOS.get(self.situacao, self.situacao)


def ultima_manutencao_do_plano(plano, historico=None):
    if historico is not None:
        itens = [
            item
            for item in historico
            if item.plano_id == plano.pk
        ]
        if not itens:
            return None
        return max(itens, key=lambda item: (item.data_realizacao, item.km_realizacao, item.pk))
    return (
        plano.historico.order_by("-data_realizacao", "-km_realizacao", "-id")
        .first()
    )


def _situacao_com_historico(plano, km_atual, hoje, km_restantes, dias_restantes):
    atrasada_km = (
        plano.intervalo_km is not None
        and km_restantes is not None
        and km_restantes <= 0
    )
    atrasada_data = (
        plano.intervalo_meses is not None
        and dias_restantes is not None
        and dias_restantes <= 0
    )
    if atrasada_km or atrasada_data:
        return SITUACAO_ATRASADA

    alerta_km = plano.antecedencia_alerta_km or 0
    alerta_dias = plano.antecedencia_alerta_dias or 0
    proxima_km = (
        plano.intervalo_km is not None
        and km_restantes is not None
        and 0 < km_restantes <= alerta_km
    )
    proxima_data = (
        plano.intervalo_meses is not None
        and dias_restantes is not None
        and 0 < dias_restantes <= alerta_dias
    )
    if proxima_km or proxima_data:
        return SITUACAO_PROXIMA
    return SITUACAO_EM_DIA


def calcular_situacao_plano(plano, veiculo=None, hoje=None, historico=None):
    veiculo = veiculo or plano.veiculo
    hoje = hoje or dia_local_atual()
    if not plano.ativo:
        return SituacaoManutencao(
            plano=plano,
            ultima=None,
            proxima_km=None,
            proxima_data=None,
            km_restantes=None,
            dias_restantes=None,
            situacao=SITUACAO_INATIVO,
        )

    ultima = ultima_manutencao_do_plano(plano, historico=historico)
    km_atual = veiculo.km_atual or 0
    proxima_km = None
    proxima_data = None
    km_restantes = None
    dias_restantes = None

    if ultima:
        if plano.intervalo_km:
            proxima_km = ultima.km_realizacao + plano.intervalo_km
            km_restantes = proxima_km - km_atual
        if plano.intervalo_meses:
            proxima_data = adicionar_meses(ultima.data_realizacao, plano.intervalo_meses)
            dias_restantes = (proxima_data - hoje).days
        situacao = _situacao_com_historico(
            plano, km_atual, hoje, km_restantes, dias_restantes
        )
    else:
        situacao = SITUACAO_SEM_HISTORICO
        if plano.intervalo_km:
            proxima_km = km_atual + plano.intervalo_km
            km_restantes = plano.intervalo_km
        if plano.intervalo_meses:
            proxima_data = adicionar_meses(hoje, plano.intervalo_meses)
            dias_restantes = (proxima_data - hoje).days

    return SituacaoManutencao(
        plano=plano,
        ultima=ultima,
        proxima_km=proxima_km,
        proxima_data=proxima_data,
        km_restantes=km_restantes,
        dias_restantes=dias_restantes,
        situacao=situacao,
    )


def situacoes_do_veiculo(veiculo, planos=None, historico=None, hoje=None):
    hoje = hoje or dia_local_atual()
    if planos is None:
        planos = list(veiculo.planos.all())
    if historico is None:
        historico = list(veiculo.manutencoes.all())
    return [
        calcular_situacao_plano(plano, veiculo=veiculo, hoje=hoje, historico=historico)
        for plano in planos
    ]


def resumo_manutencao_veiculo(situacoes):
    ativas = [item for item in situacoes if item.situacao != SITUACAO_INATIVO]
    if not ativas:
        return SITUACAO_EM_DIA, SITUACAO_ROTULOS[SITUACAO_EM_DIA]
    pior = max(ativas, key=lambda item: SITUACAO_PRIORIDADE.get(item.situacao, 0))
    return pior.situacao, pior.rotulo
