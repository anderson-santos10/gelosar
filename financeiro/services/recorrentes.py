from dataclasses import dataclass, field
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from financeiro.models import ContaPagar, ContaRecorrente


def primeiro_dia_mes(referencia):
    return date(referencia.year, referencia.month, 1)


def competencia_no_periodo(recorrente, competencia):
    competencia = primeiro_dia_mes(competencia)
    inicio = primeiro_dia_mes(recorrente.data_inicio)
    if competencia < inicio:
        return False
    if recorrente.data_fim:
        fim = primeiro_dia_mes(recorrente.data_fim)
        if competencia > fim:
            return False
    return True


def _texto_validacao(erro):
    if getattr(erro, "message_dict", None):
        partes = []
        for mensagens in erro.message_dict.values():
            if isinstance(mensagens, (list, tuple)):
                partes.extend(str(item) for item in mensagens)
            else:
                partes.append(str(mensagens))
        return " ".join(partes).strip()
    if getattr(erro, "messages", None):
        return " ".join(str(item) for item in erro.messages)
    return str(erro)


@dataclass
class ResultadoGeracao:
    conta: ContaPagar | None = None
    criada: bool = False
    ja_existia: bool = False
    ignorada_inativa: bool = False
    ignorada_vigencia: bool = False
    erro: bool = False
    motivo: str = ""


@dataclass
class ErroGeracao:
    recorrente: ContaRecorrente
    descricao: str
    motivo: str


@dataclass
class ResumoGeracao:
    criadas: int = 0
    existentes: int = 0
    inativas: int = 0
    fora_vigencia: int = 0
    competencia: date | None = None
    erros: list = field(default_factory=list)


def gerar_conta_recorrente(recorrente, competencia, criado_por=None):
    """
    Gera uma ContaPagar para a competência (1º dia do mês).
    Não altera contas já existentes. Seguro contra execução duplicada.
    """
    competencia = primeiro_dia_mes(competencia)

    if not recorrente.ativa:
        return ResultadoGeracao(ignorada_inativa=True)

    if not competencia_no_periodo(recorrente, competencia):
        return ResultadoGeracao(ignorada_vigencia=True)

    existente = ContaPagar.objects.filter(
        recorrente=recorrente,
        competencia=competencia,
    ).first()
    if existente:
        return ResultadoGeracao(conta=existente, ja_existia=True)

    categoria = getattr(recorrente, "categoria", None)
    if categoria and categoria.exige_veiculo:
        return ResultadoGeracao(
            erro=True,
            motivo=ContaRecorrente.MENSAGEM_CATEGORIA_EXIGE_VEICULO,
        )

    vencimento = date(
        competencia.year,
        competencia.month,
        recorrente.dia_vencimento,
    )
    conta = ContaPagar(
        descricao=recorrente.descricao,
        categoria=recorrente.categoria,
        fornecedor=recorrente.fornecedor,
        competencia=competencia,
        valor=recorrente.valor,
        data_vencimento=vencimento,
        status=ContaPagar.STATUS_PENDENTE,
        data_pagamento=None,
        recorrente=recorrente,
        criado_por=criado_por,
    )
    try:
        with transaction.atomic():
            conta.full_clean()
            conta.save()
    except IntegrityError:
        existente = ContaPagar.objects.filter(
            recorrente=recorrente,
            competencia=competencia,
        ).first()
        return ResultadoGeracao(conta=existente, ja_existia=True)
    except ValidationError as erro:
        return ResultadoGeracao(erro=True, motivo=_texto_validacao(erro))

    return ResultadoGeracao(conta=conta, criada=True)


def gerar_competencia(mes, ano, criado_por=None):
    competencia = date(int(ano), int(mes), 1)
    resumo = ResumoGeracao(competencia=competencia)
    recorrentes = ContaRecorrente.objects.select_related(
        "categoria",
        "fornecedor",
    ).order_by("descricao")

    for recorrente in recorrentes:
        resultado = gerar_conta_recorrente(
            recorrente,
            competencia,
            criado_por=criado_por,
        )
        if resultado.criada:
            resumo.criadas += 1
        elif resultado.ja_existia:
            resumo.existentes += 1
        elif resultado.ignorada_inativa:
            resumo.inativas += 1
        elif resultado.ignorada_vigencia:
            resumo.fora_vigencia += 1
        elif resultado.erro:
            resumo.erros.append(
                ErroGeracao(
                    recorrente=recorrente,
                    descricao=recorrente.descricao,
                    motivo=resultado.motivo,
                )
            )
    return resumo
