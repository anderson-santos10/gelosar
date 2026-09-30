from dataclasses import dataclass, field

from django.db import transaction

from financeiro.models import ObrigacaoVeiculo, Veiculo
from financeiro.services.ipva import avaliar_ipva


@dataclass
class ResultadoObrigacoes:
    criadas: int = 0
    atualizadas: int = 0
    preservadas: int = 0
    ipva: ObrigacaoVeiculo | None = None
    licenciamento: ObrigacaoVeiculo | None = None
    detalhes: list = field(default_factory=list)


STATUS_PRESERVADOS = {
    ObrigacaoVeiculo.STATUS_PAGO,
    ObrigacaoVeiculo.STATUS_CANCELADO,
    ObrigacaoVeiculo.STATUS_NAO_APLICAVEL,
}


def _status_ipva(situacao):
    if not situacao.determinado:
        return None
    if situacao.isento:
        return ObrigacaoVeiculo.STATUS_ISENTO
    return ObrigacaoVeiculo.STATUS_PENDENTE


def _mapa_obrigacoes(veiculos, exercicio):
    ids = [veiculo.pk for veiculo in veiculos if getattr(veiculo, "pk", None)]
    if not ids:
        return {}
    existentes = ObrigacaoVeiculo.objects.filter(
        veiculo_id__in=ids,
        exercicio=int(exercicio),
        tipo__in=(
            ObrigacaoVeiculo.TIPO_IPVA,
            ObrigacaoVeiculo.TIPO_LICENCIAMENTO,
        ),
    )
    return {(item.veiculo_id, item.tipo): item for item in existentes}


def _gerar_ipva(veiculo, exercicio, situacao_ipva, resultado, existente=None, consultado=False):
    status_ipva = _status_ipva(situacao_ipva)
    if not consultado:
        existente = ObrigacaoVeiculo.objects.filter(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_IPVA,
            exercicio=exercicio,
        ).first()

    if status_ipva is None:
        resultado.detalhes.append(situacao_ipva.motivo)
        if existente:
            resultado.preservadas += 1
            resultado.detalhes.append("IPVA existente preservado.")
            resultado.ipva = existente
        else:
            resultado.detalhes.append(
                "IPVA não gerado: situação não determinada."
            )
            resultado.ipva = None
        return

    if existente is None:
        ipva, criado = ObrigacaoVeiculo.objects.get_or_create(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_IPVA,
            exercicio=exercicio,
            defaults={
                "status": status_ipva,
                "observacoes": situacao_ipva.motivo,
            },
        )
    else:
        ipva, criado = existente, False

    if criado:
        resultado.criadas += 1
        resultado.detalhes.append("IPVA criado.")
    elif ipva.status in STATUS_PRESERVADOS:
        resultado.preservadas += 1
        resultado.detalhes.append("IPVA existente preservado.")
    else:
        campos = []
        if ipva.status != status_ipva:
            ipva.status = status_ipva
            campos.append("status")
        if situacao_ipva.motivo and situacao_ipva.motivo not in (ipva.observacoes or ""):
            ipva.observacoes = situacao_ipva.motivo
            campos.append("observacoes")
        if campos:
            ipva.save(update_fields=campos + ["atualizado_em"])
            resultado.atualizadas += 1
            resultado.detalhes.append("IPVA atualizado.")
        else:
            resultado.preservadas += 1
            resultado.detalhes.append("IPVA já estava em dia com a regra.")
    resultado.ipva = ipva


def _gerar_licenciamento(veiculo, exercicio, resultado, existente=None, consultado=False):
    if not consultado:
        licenciamento, criado = ObrigacaoVeiculo.objects.get_or_create(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_LICENCIAMENTO,
            exercicio=exercicio,
            defaults={"status": ObrigacaoVeiculo.STATUS_PENDENTE},
        )
    elif existente is None:
        licenciamento, criado = ObrigacaoVeiculo.objects.get_or_create(
            veiculo=veiculo,
            tipo=ObrigacaoVeiculo.TIPO_LICENCIAMENTO,
            exercicio=exercicio,
            defaults={"status": ObrigacaoVeiculo.STATUS_PENDENTE},
        )
    else:
        licenciamento, criado = existente, False

    if criado:
        resultado.criadas += 1
        resultado.detalhes.append("Licenciamento criado.")
    else:
        resultado.preservadas += 1
        resultado.detalhes.append("Licenciamento existente preservado.")
    resultado.licenciamento = licenciamento


def _gerar_obrigacoes_veiculo(veiculo, exercicio, mapa=None):
    resultado = ResultadoObrigacoes()
    situacao_ipva = avaliar_ipva(veiculo, exercicio)
    consultado = mapa is not None
    existente_ipva = (
        mapa.get((veiculo.pk, ObrigacaoVeiculo.TIPO_IPVA)) if mapa is not None else None
    )
    existente_lic = (
        mapa.get((veiculo.pk, ObrigacaoVeiculo.TIPO_LICENCIAMENTO))
        if mapa is not None
        else None
    )
    _gerar_ipva(
        veiculo,
        exercicio,
        situacao_ipva,
        resultado,
        existente=existente_ipva,
        consultado=consultado,
    )
    _gerar_licenciamento(
        veiculo,
        exercicio,
        resultado,
        existente=existente_lic,
        consultado=consultado,
    )
    return resultado


@transaction.atomic
def gerar_obrigacoes_exercicio(veiculo, exercicio):
    exercicio = int(exercicio)
    return _gerar_obrigacoes_veiculo(veiculo, exercicio)


@transaction.atomic
def gerar_obrigacoes_frota(exercicio, veiculos=None):
    exercicio = int(exercicio)
    if veiculos is None:
        veiculos = Veiculo.objects.filter(ativo=True)
    veiculos = list(veiculos)
    mapa = _mapa_obrigacoes(veiculos, exercicio)
    consolidado = ResultadoObrigacoes()
    for veiculo in veiculos:
        parcial = _gerar_obrigacoes_veiculo(veiculo, exercicio, mapa=mapa)
        consolidado.criadas += parcial.criadas
        consolidado.atualizadas += parcial.atualizadas
        consolidado.preservadas += parcial.preservadas
    return consolidado
