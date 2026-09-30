from dataclasses import dataclass

SITUACAO_DEVIDO = "devido"
SITUACAO_ISENTO = "isento"
SITUACAO_NAO_DETERMINADO = "nao_determinado"

# Regras de isenção por UF e exercício.
# Atualize este mapa quando a legislação mudar; não espalhe a regra em views/templates.
REGRAS_ISENCAO_IPVA = {
    ("SP", 2026): {
        "ano_fabricacao_maximo_isento": 2005,
        "motivo_isento": (
            "Em São Paulo, no exercício de 2026, automóveis fabricados até 2005 "
            "são isentos de IPVA."
        ),
        "motivo_devido": (
            "Em São Paulo, no exercício de 2026, o veículo não se enquadra na "
            "isenção por ano de fabricação."
        ),
    },
}

MOTIVO_ANO_AUSENTE = (
    "Informe o ano de fabricação do veículo para determinar a situação do IPVA."
)


@dataclass(frozen=True)
class SituacaoIPVA:
    aplicavel: bool
    isento: bool
    determinado: bool
    motivo: str
    uf: str
    exercicio: int
    ano_fabricacao: int | None
    situacao: str

    @property
    def rotulo(self):
        if self.situacao == SITUACAO_ISENTO:
            return "ISENTO"
        if self.situacao == SITUACAO_DEVIDO:
            return "DEVIDO"
        return "NÃO DETERMINADO"


def regra_ipva(uf, exercicio):
    return REGRAS_ISENCAO_IPVA.get((str(uf or "").upper(), int(exercicio)))


def _ano_fabricacao(veiculo):
    valor = getattr(veiculo, "ano_fabricacao", None)
    if valor in (None, ""):
        return None
    try:
        ano = int(valor)
    except (TypeError, ValueError):
        return None
    if ano <= 0:
        return None
    return ano


def _nao_determinado(uf, exercicio, ano_fabricacao, motivo):
    return SituacaoIPVA(
        aplicavel=False,
        isento=False,
        determinado=False,
        motivo=motivo,
        uf=uf,
        exercicio=int(exercicio),
        ano_fabricacao=ano_fabricacao,
        situacao=SITUACAO_NAO_DETERMINADO,
    )


def avaliar_ipva(veiculo, exercicio):
    uf = str(getattr(veiculo, "uf", "") or "").upper()
    ano_fabricacao = _ano_fabricacao(veiculo)
    regra = regra_ipva(uf, exercicio)

    if regra is None:
        return _nao_determinado(
            uf,
            exercicio,
            ano_fabricacao,
            (
                "Não há regra automática de IPVA cadastrada para esta UF e exercício. "
                "Informe a obrigação manualmente."
            ),
        )

    if ano_fabricacao is None:
        return _nao_determinado(uf, exercicio, None, MOTIVO_ANO_AUSENTE)

    limite = regra["ano_fabricacao_maximo_isento"]
    isento = ano_fabricacao <= limite
    return SituacaoIPVA(
        aplicavel=not isento,
        isento=isento,
        determinado=True,
        motivo=regra["motivo_isento"] if isento else regra["motivo_devido"],
        uf=uf,
        exercicio=int(exercicio),
        ano_fabricacao=ano_fabricacao,
        situacao=SITUACAO_ISENTO if isento else SITUACAO_DEVIDO,
    )
