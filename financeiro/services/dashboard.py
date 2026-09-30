from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.urls import reverse

from core.periodo import dia_local_atual
from financeiro.models import (
    ContaPagar,
    ContaRecorrente,
    ObrigacaoVeiculo,
    PlanoManutencao,
    ManutencaoVeiculo,
    Veiculo,
)
from financeiro.services.agregacao import (
    JANELA_VENCIMENTO_DIAS,
    ZERO,
    ZERO_AGG,
    agregar as _agregar,
    chart_valores as _chart_valores,
    percentual as _percentual,
    quantize as _quantize,
    variacao as _variacao,
)
from financeiro.services.manutencao import (
    resumo_manutencao_veiculo,
    situacoes_do_veiculo,
)
from financeiro.services.periodo import (
    LIMITE_DIAS_AGRUPAMENTO_DIARIO,
    PERIODO_ESTE_ANO,
    PERIODO_ESTE_MES,
    PERIODO_MES_ANTERIOR,
    PERIODO_OPCOES,
    PERIODO_PERSONALIZADO,
    PERIODO_ULTIMOS_3,
    PERIODO_ULTIMOS_6,
    deslocar_meses,
    periodo_anterior_equivalente,
    resolver_periodo,
)
from financeiro.services.recorrentes import competencia_no_periodo, primeiro_dia_mes

LIMITE_PROXIMOS_VENCIMENTOS = 8
LIMITE_VENCIDAS = 8
LIMITE_VEICULOS = 8


def _pagas_no_periodo(inicio, fim):
    return ContaPagar.objects.filter(
        status=ContaPagar.STATUS_PAGO,
        data_pagamento__gte=inicio,
        data_pagamento__lte=fim,
    )


@dataclass
class Indicador:
    quantidade: int
    total: Decimal
    url: str = ""

    @property
    def visivel(self):
        return self.quantidade > 0


@dataclass
class LinhaCategoria:
    nome: str
    quantidade: int
    total: Decimal
    percentual: Decimal


@dataclass
class DashboardFinanceiro:
    periodo: str
    inicio: date
    fim: date
    anterior_inicio: date
    anterior_fim: date
    pendentes: Indicador
    vencidas: Indicador
    vencendo: Indicador
    pagas: Indicador
    comparacao_percentual: Decimal | None
    comparacao_atual: Decimal
    comparacao_anterior: Decimal
    chart_categorias: dict
    chart_evolucao: dict
    categorias: list = field(default_factory=list)
    proximos_vencimentos: list = field(default_factory=list)
    contas_vencidas: list = field(default_factory=list)
    recorrencias: list = field(default_factory=list)
    veiculos: list = field(default_factory=list)
    gastos_veiculos: Indicador | None = None
    ranking_veiculos: list = field(default_factory=list)
    manutencao: Indicador | None = None
    manutencao_maior_veiculo: str = ""
    obrigacoes: list = field(default_factory=list)
    sem_fornecedor: Indicador | None = None
    formas_pagamento: list = field(default_factory=list)
    janela_dias: int = JANELA_VENCIMENTO_DIAS

    @property
    def querystring(self):
        return urlencode(
            {
                "periodo": self.periodo,
                "inicio": self.inicio.isoformat(),
                "fim": self.fim.isoformat(),
            }
        )


def _indicador_contas(queryset, url):
    quantidade, total = _agregar(queryset)
    return Indicador(quantidade=quantidade, total=total, url=url)


def _evolucao(pagas, inicio, fim):
    dias = (fim - inicio).days + 1
    if dias <= LIMITE_DIAS_AGRUPAMENTO_DIARIO:
        rows = pagas.values("data_pagamento").annotate(total=Sum("valor"))
        por_dia = {row["data_pagamento"]: _quantize(row["total"]) for row in rows}
        labels = []
        valores = []
        atual = inicio
        while atual <= fim:
            labels.append(atual.strftime("%d/%m"))
            valores.append(por_dia.get(atual, ZERO))
            atual += timedelta(days=1)
        return _chart_valores(labels, valores)
    rows = (
        pagas.annotate(mes=TruncMonth("data_pagamento"))
        .values("mes")
        .annotate(total=Sum("valor"))
        .order_by("mes")
    )
    por_mes = {}
    for row in rows:
        mes = row["mes"]
        if hasattr(mes, "date"):
            mes = mes.date()
        por_mes[date(mes.year, mes.month, 1)] = _quantize(row["total"])
    labels = []
    valores = []
    cursor = date(inicio.year, inicio.month, 1)
    limite = date(fim.year, fim.month, 1)
    nomes = (
        "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
        "Jul", "Ago", "Set", "Out", "Nov", "Dez",
    )
    while cursor <= limite:
        labels.append(f"{nomes[cursor.month - 1]}/{cursor.year}")
        valores.append(por_mes.get(cursor, ZERO))
        cursor = deslocar_meses(cursor, 1)
    return _chart_valores(labels, valores)


def _categorias_pagas(pagas, total_pago):
    rows = (
        pagas.values("categoria__nome")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("-total")
    )
    linhas = []
    labels = []
    valores = []
    for row in rows:
        total = _quantize(row["total"])
        linhas.append(
            LinhaCategoria(
                nome=row["categoria__nome"],
                quantidade=int(row["quantidade"] or 0),
                total=total,
                percentual=_percentual(total, total_pago),
            )
        )
        labels.append(row["categoria__nome"])
        valores.append(total)
    chart = _chart_valores(labels, valores, tipo="doughnut", label="Pago", legenda=True)
    return linhas, chart


def _proximas_recorrencias(hoje):
    competencia = primeiro_dia_mes(hoje)
    recorrentes = list(
        ContaRecorrente.objects.filter(ativa=True)
        .select_related("categoria")
        .annotate(
            gerada=Count(
                "contas_geradas",
                filter=Q(contas_geradas__competencia=competencia),
            )
        )
        .order_by("dia_vencimento", "descricao")
    )
    proximas = []
    for item in recorrentes:
        if not competencia_no_periodo(item, competencia):
            continue
        if item.gerada:
            continue
        proximas.append(item)
    return proximas


def _bloco_veiculos(hoje, incluir):
    if not incluir:
        return [], []
    veiculos = list(
        Veiculo.objects.filter(ativo=True)
        .prefetch_related(
            Prefetch("planos", queryset=PlanoManutencao.objects.order_by("nome")),
            Prefetch(
                "manutencoes",
                queryset=ManutencaoVeiculo.objects.order_by(
                    "-data_realizacao", "-km_realizacao"
                ),
            ),
            Prefetch(
                "obrigacoes",
                queryset=ObrigacaoVeiculo.objects.filter(
                    status=ObrigacaoVeiculo.STATUS_PENDENTE
                ).order_by("data_vencimento", "tipo"),
            ),
        )
        .order_by("marca", "modelo")[:LIMITE_VEICULOS]
    )
    linhas = []
    for veiculo in veiculos:
        situacoes = situacoes_do_veiculo(
            veiculo,
            planos=list(veiculo.planos.all()),
            historico=list(veiculo.manutencoes.all()),
            hoje=hoje,
        )
        codigo, rotulo = resumo_manutencao_veiculo(situacoes)
        obrigacao = next(iter(veiculo.obrigacoes.all()), None)
        linhas.append(
            {
                "veiculo": veiculo,
                "manutencao_codigo": codigo,
                "manutencao_rotulo": rotulo,
                "proxima_obrigacao": obrigacao,
            }
        )
    obrigacoes = list(
        ObrigacaoVeiculo.objects.filter(
            status=ObrigacaoVeiculo.STATUS_PENDENTE,
            veiculo__ativo=True,
        )
        .exclude(tipo=ObrigacaoVeiculo.TIPO_IPVA, status=ObrigacaoVeiculo.STATUS_ISENTO)
        .select_related("veiculo")
        .order_by("data_vencimento", "tipo")[:12]
    )
    alertas = []
    for item in obrigacoes:
        if item.tipo == ObrigacaoVeiculo.TIPO_IPVA and item.status == ObrigacaoVeiculo.STATUS_ISENTO:
            continue
        vencida = bool(item.data_vencimento and item.data_vencimento < hoje)
        alertas.append({"obrigacao": item, "vencida": vencida})
    return linhas, alertas


def montar_dashboard(params, permissoes=None, hoje=None):
    hoje = hoje or dia_local_atual()
    permissoes = permissoes or set()
    chave, inicio, fim = resolver_periodo(params, hoje=hoje)
    ant_inicio, ant_fim = periodo_anterior_equivalente(chave, inicio, fim)
    janela_fim = hoje + timedelta(days=JANELA_VENCIMENTO_DIAS)

    url_pendentes = reverse("financeiro:lista_contas_pagar") + "?status=pendente"
    url_vencidas = reverse("financeiro:lista_contas_pagar") + "?status=vencida"
    url_pagas = reverse("financeiro:lista_contas_pagar") + "?status=pago"

    pendentes_qs = ContaPagar.objects.filter(
        status=ContaPagar.STATUS_PENDENTE,
        data_vencimento__gte=hoje,
    )
    vencidas_qs = ContaPagar.objects.filter(
        status=ContaPagar.STATUS_PENDENTE,
        data_vencimento__lt=hoje,
    )
    vencendo_qs = ContaPagar.objects.filter(
        status=ContaPagar.STATUS_PENDENTE,
        data_vencimento__gte=hoje,
        data_vencimento__lte=janela_fim,
    )
    pagas = _pagas_no_periodo(inicio, fim)
    pagas_ant = _pagas_no_periodo(ant_inicio, ant_fim)

    pendentes = _indicador_contas(pendentes_qs, url_pendentes)
    vencidas = _indicador_contas(vencidas_qs, url_vencidas)
    vencendo = _indicador_contas(vencendo_qs, url_pendentes)
    indicador_pagas = _indicador_contas(pagas, url_pagas)
    total_pago = indicador_pagas.total
    total_anterior = _agregar(pagas_ant)[1]

    categorias, chart_categorias = _categorias_pagas(pagas, total_pago)
    if not categorias:
        chart_categorias = _chart_valores([], [], tipo="doughnut", label="Pago", legenda=True)
    chart_evolucao = _evolucao(pagas, inicio, fim)
    if indicador_pagas.quantidade == 0:
        chart_evolucao = _chart_valores([], [])

    proximos = list(
        pendentes_qs.select_related("categoria", "fornecedor").order_by(
            "data_vencimento", "id"
        )[:LIMITE_PROXIMOS_VENCIMENTOS]
    )
    lista_vencidas = list(
        vencidas_qs.select_related("fornecedor").order_by("data_vencimento", "id")[
            :LIMITE_VENCIDAS
        ]
    )
    for conta in lista_vencidas:
        conta.dias_atraso = (hoje - conta.data_vencimento).days

    recorrencias = []
    if "financeiro.view_contarecorrente" in permissoes:
        recorrencias = _proximas_recorrencias(hoje)

    veiculos = []
    obrigacoes = []
    gastos_veiculos = None
    ranking = []
    manutencao = None
    maior_veiculo = ""
    if "financeiro.view_veiculo" in permissoes:
        veiculos, obrigacoes = _bloco_veiculos(hoje, True)
        veic_qs = pagas.filter(veiculo__isnull=False)
        qtd_v, tot_v = _agregar(veic_qs)
        if qtd_v:
            gastos_veiculos = Indicador(
                quantidade=qtd_v,
                total=tot_v,
                url=reverse("financeiro:lista_veiculos"),
            )
            ranking = [
                {
                    "veiculo": row["veiculo__marca"] + " " + row["veiculo__modelo"],
                    "placa": row["veiculo__placa"],
                    "total": _quantize(row["total"]),
                }
                for row in veic_qs.values(
                    "veiculo__marca", "veiculo__modelo", "veiculo__placa"
                )
                .annotate(total=Sum("valor"))
                .order_by("-total")[:5]
            ]
        man_qs = pagas.filter(manutencao__isnull=False)
        qtd_m, tot_m = _agregar(man_qs)
        if qtd_m:
            manutencao = Indicador(quantidade=qtd_m, total=tot_m)
            top = (
                man_qs.values("veiculo__marca", "veiculo__modelo")
                .annotate(total=Sum("valor"))
                .order_by("-total")
                .first()
            )
            if top and top.get("veiculo__marca"):
                maior_veiculo = f"{top['veiculo__marca']} {top['veiculo__modelo']}"

    sem_qs = ContaPagar.objects.filter(fornecedor__isnull=True).exclude(
        status=ContaPagar.STATUS_CANCELADO
    )
    qtd_sf, tot_sf = _agregar(sem_qs)
    sem_fornecedor = None
    if qtd_sf:
        sem_fornecedor = Indicador(
            quantidade=qtd_sf,
            total=tot_sf,
            url=reverse("financeiro:lista_contas_pagar") + "?sem_fornecedor=1",
        )

    formas = []
    forma_rows = (
        pagas.exclude(forma_pagamento="")
        .values("forma_pagamento")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("-total")
    )
    mapa_formas = dict(ContaPagar.FORMA_CHOICES)
    forma_lista = list(forma_rows)
    if len(forma_lista) >= 2:
        for row in forma_lista:
            formas.append(
                {
                    "nome": mapa_formas.get(row["forma_pagamento"], row["forma_pagamento"]),
                    "quantidade": int(row["quantidade"] or 0),
                    "total": _quantize(row["total"]),
                }
            )

    return DashboardFinanceiro(
        periodo=chave,
        inicio=inicio,
        fim=fim,
        anterior_inicio=ant_inicio,
        anterior_fim=ant_fim,
        pendentes=pendentes,
        vencidas=vencidas,
        vencendo=vencendo,
        pagas=indicador_pagas,
        comparacao_percentual=_variacao(total_pago, total_anterior),
        comparacao_atual=total_pago,
        comparacao_anterior=total_anterior,
        chart_categorias=chart_categorias,
        chart_evolucao=chart_evolucao,
        categorias=categorias,
        proximos_vencimentos=proximos,
        contas_vencidas=lista_vencidas,
        recorrencias=recorrencias,
        veiculos=veiculos,
        gastos_veiculos=gastos_veiculos,
        ranking_veiculos=ranking,
        manutencao=manutencao,
        manutencao_maior_veiculo=maior_veiculo,
        obrigacoes=obrigacoes,
        sem_fornecedor=sem_fornecedor,
        formas_pagamento=formas,
    )
