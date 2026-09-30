from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Avg, Count, DecimalField, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from core.periodo import dia_local_atual
from financeiro.models import (
    CategoriaFinanceira,
    ContaPagar,
    Fornecedor,
    ObrigacaoVeiculo,
    Veiculo,
)
from financeiro.placas import formatar_placa
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
from financeiro.services.periodo import (
    LIMITE_DIAS_AGRUPAMENTO_DIARIO,
    deslocar_meses,
    periodo_anterior_equivalente,
    resolver_periodo,
)
LIMITE_TOP_FORNECEDORES = 8
LIMITE_COMPROMISSOS = 10
NOMES_MES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
NOMES_MES_CURTO = (
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
)


def _pk(params, nome):
    bruto = (params.get(nome) or "").strip()
    if bruto.isdigit():
        return int(bruto)
    return None


def aplicar_filtros_despesas(queryset, params):
    categoria_id = _pk(params, "categoria")
    if categoria_id is not None:
        if not CategoriaFinanceira.objects.filter(pk=categoria_id).exists():
            return queryset.none()
        queryset = queryset.filter(categoria_id=categoria_id)

    fornecedor_id = _pk(params, "fornecedor")
    if fornecedor_id is not None:
        if not Fornecedor.objects.filter(pk=fornecedor_id).exists():
            return queryset.none()
        queryset = queryset.filter(fornecedor_id=fornecedor_id)

    veiculo_id = _pk(params, "veiculo")
    if veiculo_id is not None:
        if not Veiculo.objects.filter(pk=veiculo_id).exists():
            return queryset.none()
        queryset = queryset.filter(veiculo_id=veiculo_id)

    forma = (params.get("forma") or "").strip()
    formas_validas = {item[0] for item in ContaPagar.FORMA_CHOICES}
    if forma:
        if forma not in formas_validas:
            return queryset.none()
        queryset = queryset.filter(forma_pagamento=forma)
    return queryset


def contas_pagas_filtradas(params, inicio, fim):
    queryset = ContaPagar.objects.filter(
        status=ContaPagar.STATUS_PAGO,
        data_pagamento__gte=inicio,
        data_pagamento__lte=fim,
    )
    return aplicar_filtros_despesas(queryset, params)


def _linhas_percentuais(rows, total, nome_key, extra=None):
    linhas = []
    for row in rows:
        valor = _quantize(row["total"])
        item = {
            "nome": row[nome_key] or "Sem fornecedor",
            "quantidade": int(row["quantidade"] or 0),
            "total": valor,
            "percentual": _percentual(valor, total),
        }
        if extra:
            item.update(extra(row))
        linhas.append(item)
    return linhas


def _evolucao(pagas, inicio, fim):
    dias = (fim - inicio).days + 1
    linhas = []
    labels = []
    valores = []
    if dias <= LIMITE_DIAS_AGRUPAMENTO_DIARIO:
        rows = pagas.values("data_pagamento").annotate(
            quantidade=Count("id"),
            total=Sum("valor"),
        )
        por_dia = {
            row["data_pagamento"]: (
                int(row["quantidade"] or 0),
                _quantize(row["total"]),
            )
            for row in rows
        }
        atual = inicio
        while atual <= fim:
            qtd, total = por_dia.get(atual, (0, ZERO))
            rotulo = atual.strftime("%d/%m")
            linhas.append({"rotulo": rotulo, "quantidade": qtd, "total": total})
            labels.append(rotulo)
            valores.append(total)
            atual += timedelta(days=1)
        agrupamento = "diario"
    else:
        rows = (
            pagas.annotate(mes=TruncMonth("data_pagamento"))
            .values("mes")
            .annotate(quantidade=Count("id"), total=Sum("valor"))
        )
        por_mes = {}
        for row in rows:
            mes = row["mes"]
            if hasattr(mes, "date"):
                mes = mes.date()
            chave = date(mes.year, mes.month, 1)
            por_mes[chave] = (int(row["quantidade"] or 0), _quantize(row["total"]))
        cursor = date(inicio.year, inicio.month, 1)
        limite = date(fim.year, fim.month, 1)
        while cursor <= limite:
            qtd, total = por_mes.get(cursor, (0, ZERO))
            rotulo = f"{NOMES_MES_CURTO[cursor.month - 1]}/{cursor.year}"
            linhas.append({"rotulo": rotulo, "quantidade": qtd, "total": total})
            labels.append(rotulo)
            valores.append(total)
            cursor = deslocar_meses(cursor, 1)
        agrupamento = "mensal"
    return linhas, _chart_valores(labels, valores), agrupamento


def _mensal_consolidado(pagas, inicio, fim):
    totais = (
        pagas.annotate(mes=TruncMonth("data_pagamento"))
        .values("mes")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("mes")
    )
    cats = (
        pagas.annotate(mes=TruncMonth("data_pagamento"))
        .values("mes", "categoria__nome")
        .annotate(total=Sum("valor"))
    )
    forns = (
        pagas.annotate(mes=TruncMonth("data_pagamento"))
        .values("mes", "fornecedor__nome")
        .annotate(total=Sum("valor"))
    )

    def _chave_mes(valor):
        if hasattr(valor, "date"):
            valor = valor.date()
        return date(valor.year, valor.month, 1)

    melhor_cat = {}
    for row in cats:
        chave = _chave_mes(row["mes"])
        atual = melhor_cat.get(chave)
        total = _quantize(row["total"])
        if atual is None or total > atual[1]:
            melhor_cat[chave] = (row["categoria__nome"], total)
    melhor_forn = {}
    for row in forns:
        chave = _chave_mes(row["mes"])
        atual = melhor_forn.get(chave)
        total = _quantize(row["total"])
        nome = row["fornecedor__nome"] or "Sem fornecedor"
        if atual is None or total > atual[1]:
            melhor_forn[chave] = (nome, total)

    linhas = []
    for row in totais:
        chave = _chave_mes(row["mes"])
        cat = melhor_cat.get(chave, ("—", ZERO))[0]
        forn = melhor_forn.get(chave, ("—", ZERO))[0]
        linhas.append(
            {
                "rotulo": f"{NOMES_MES[chave.month - 1]} {chave.year}",
                "quantidade": int(row["quantidade"] or 0),
                "total": _quantize(row["total"]),
                "maior_categoria": cat,
                "maior_fornecedor": forn,
            }
        )
    return linhas


def _veiculos_e_categorias(pagas, total_pago):
    totais = (
        pagas.values("veiculo_id", "veiculo__marca", "veiculo__modelo", "veiculo__placa")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("-total")
    )
    detalhe = (
        pagas.values(
            "veiculo_id",
            "categoria__nome",
            "categoria__slug",
        )
        .annotate(total=Sum("valor"))
        .order_by("veiculo_id", "-total")
    )
    por_veiculo = defaultdict(list)
    for row in detalhe:
        por_veiculo[row["veiculo_id"]].append(
            {
                "nome": row["categoria__nome"],
                "slug": row["categoria__slug"],
                "total": _quantize(row["total"]),
            }
        )
    linhas = []
    for row in totais:
        veiculo_id = row["veiculo_id"]
        if veiculo_id:
            nome = f"{row['veiculo__marca']} {row['veiculo__modelo']}"
            placa = formatar_placa(row["veiculo__placa"] or "")
        else:
            nome = "Sem veículo"
            placa = "—"
        total = _quantize(row["total"])
        linhas.append(
            {
                "id": veiculo_id,
                "nome": nome,
                "placa": placa,
                "quantidade": int(row["quantidade"] or 0),
                "total": total,
                "percentual": _percentual(total, total_pago),
                "categorias": por_veiculo.get(veiculo_id, []),
            }
        )
    return linhas


def _manutencao_por_veiculo(pagas):
    rows = (
        pagas.filter(manutencao_id__isnull=False)
        .values("veiculo_id", "veiculo__marca", "veiculo__modelo", "veiculo__placa")
        .annotate(
            qtd_contas=Count("id"),
            qtd_manutencoes=Count("manutencao_id", distinct=True),
            total=Sum("valor"),
        )
        .order_by("-total")
    )
    linhas = []
    for row in rows:
        if row["veiculo_id"]:
            nome = f"{row['veiculo__marca']} {row['veiculo__modelo']}"
            placa = formatar_placa(row["veiculo__placa"] or "")
        else:
            nome = "Sem veículo"
            placa = "—"
        linhas.append(
            {
                "nome": nome,
                "placa": placa,
                "qtd_manutencoes": int(row["qtd_manutencoes"] or 0),
                "qtd_contas": int(row["qtd_contas"] or 0),
                "total": _quantize(row["total"]),
            }
        )
    return linhas


def _obrigacoes(params, permissoes, hoje):
    if "financeiro.view_obrigacaoveiculo" not in permissoes:
        return []
    queryset = ObrigacaoVeiculo.objects.select_related("veiculo")
    veiculo_id = _pk(params, "veiculo")
    if veiculo_id is not None:
        queryset = queryset.filter(veiculo_id=veiculo_id)
    tipo = (params.get("tipo") or "").strip()
    tipos = {item[0] for item in ObrigacaoVeiculo.TIPO_CHOICES}
    if tipo:
        if tipo not in tipos:
            return []
        queryset = queryset.filter(tipo=tipo)
    status = (params.get("status_obrigacao") or "").strip()
    status_ok = {item[0] for item in ObrigacaoVeiculo.STATUS_CHOICES}
    if status:
        if status not in status_ok:
            return []
        queryset = queryset.filter(status=status)
    exercicio = _pk(params, "exercicio")
    if exercicio is not None:
        queryset = queryset.filter(exercicio=exercicio)
    linhas = []
    for item in queryset.order_by("-exercicio", "tipo", "veiculo__marca")[:80]:
        vencida = bool(
            item.status == ObrigacaoVeiculo.STATUS_PENDENTE
            and item.data_vencimento
            and item.data_vencimento < hoje
        )
        linhas.append({"obrigacao": item, "vencida": vencida})
    return linhas


def _compromissos(params, hoje):
    base = ContaPagar.objects.filter(status=ContaPagar.STATUS_PENDENTE)
    base = aplicar_filtros_despesas(base, params)
    janela_fim = hoje + timedelta(days=JANELA_VENCIMENTO_DIAS)
    pendentes = base.filter(data_vencimento__gte=hoje)
    vencidas = base.filter(data_vencimento__lt=hoje)
    vencendo = base.filter(
        data_vencimento__gte=hoje,
        data_vencimento__lte=janela_fim,
    )
    qtd_p, tot_p = _agregar(pendentes)
    qtd_v, tot_v = _agregar(vencidas)
    qtd_b, tot_b = _agregar(vencendo)
    lista_vencidas = list(
        vencidas.select_related("categoria", "fornecedor").order_by(
            "data_vencimento", "id"
        )[:LIMITE_COMPROMISSOS]
    )
    for conta in lista_vencidas:
        conta.dias_atraso = (hoje - conta.data_vencimento).days
    proximos = list(
        pendentes.select_related("categoria", "fornecedor").order_by(
            "data_vencimento", "id"
        )[:LIMITE_COMPROMISSOS]
    )
    return {
        "pendentes_qtd": qtd_p,
        "pendentes_total": tot_p,
        "vencidas_qtd": qtd_v,
        "vencidas_total": tot_v,
        "vencendo_qtd": qtd_b,
        "vencendo_total": tot_b,
        "vencidas": lista_vencidas,
        "proximos": proximos,
        "janela_dias": JANELA_VENCIMENTO_DIAS,
    }


@dataclass
class RelatorioFinanceiro:
    periodo: str
    inicio: date
    fim: date
    anterior_inicio: date
    anterior_fim: date
    filtros: dict
    quantidade: int
    total: Decimal
    media: Decimal | None
    maior: Decimal | None
    menor: Decimal | None
    comparacao_atual: Decimal
    comparacao_anterior: Decimal
    comparacao_diferenca: Decimal
    comparacao_percentual: Decimal | None
    categorias: list = field(default_factory=list)
    chart_categorias: dict = field(default_factory=dict)
    evolucao: list = field(default_factory=list)
    chart_evolucao: dict = field(default_factory=dict)
    fornecedores: list = field(default_factory=list)
    top_fornecedores: list = field(default_factory=list)
    veiculos: list = field(default_factory=list)
    manutencoes: list = field(default_factory=list)
    formas: list = field(default_factory=list)
    mensal: list = field(default_factory=list)
    obrigacoes: list = field(default_factory=list)
    compromissos: dict = field(default_factory=dict)
    categorias_filtro: list = field(default_factory=list)
    fornecedores_filtro: list = field(default_factory=list)
    veiculos_filtro: list = field(default_factory=list)

    @property
    def tem_despesas(self):
        return self.quantidade > 0

    @property
    def querystring(self):
        dados = {
            "periodo": self.periodo,
            "inicio": self.inicio.isoformat(),
            "fim": self.fim.isoformat(),
        }
        for chave, valor in self.filtros.items():
            if valor:
                dados[chave] = valor
        return urlencode(dados)


def montar_relatorio(params, permissoes=None, hoje=None):
    hoje = hoje or dia_local_atual()
    permissoes = permissoes or set()
    chave, inicio, fim = resolver_periodo(params, hoje=hoje)
    ant_inicio, ant_fim = periodo_anterior_equivalente(chave, inicio, fim)
    pagas = contas_pagas_filtradas(params, inicio, fim)
    pagas_ant = contas_pagas_filtradas(params, ant_inicio, ant_fim)

    resumo = pagas.aggregate(
        quantidade=Count("id"),
        total=Coalesce(Sum("valor"), ZERO_AGG),
        media=Avg("valor"),
        maior=Max("valor"),
        menor=Min("valor"),
    )
    quantidade = int(resumo["quantidade"] or 0)
    total = _quantize(resumo["total"])
    media = _quantize(resumo["media"]) if resumo["media"] is not None else None
    maior = _quantize(resumo["maior"]) if resumo["maior"] is not None else None
    menor = _quantize(resumo["menor"]) if resumo["menor"] is not None else None
    total_anterior = _agregar(pagas_ant)[1]

    categorias = []
    chart_categorias = _chart_valores([], [])
    if quantidade:
        cat_rows = (
            pagas.values("categoria__nome")
            .annotate(quantidade=Count("id"), total=Sum("valor"))
            .order_by("-total")
        )
        categorias = _linhas_percentuais(cat_rows, total, "categoria__nome")
        labels = [item["nome"] for item in categorias]
        valores = [item["total"] for item in categorias]
        tipo = "bar" if len(categorias) >= 6 else "doughnut"
        chart_categorias = _chart_valores(
            labels,
            valores,
            tipo=tipo,
            label="Pago",
            legenda=tipo == "doughnut",
        )
        if tipo == "bar":
            chart_categorias["indexAxis"] = "y"

    evolucao, chart_evolucao, _agrupamento = _evolucao(pagas, inicio, fim)
    if not quantidade:
        evolucao = []
        chart_evolucao = _chart_valores([], [])

    forn_rows = (
        pagas.values("fornecedor_id", "fornecedor__nome")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("-total")
    )
    fornecedores = []
    for row in forn_rows:
        valor = _quantize(row["total"])
        fornecedores.append(
            {
                "id": row["fornecedor_id"],
                "nome": row["fornecedor__nome"] or "Sem fornecedor",
                "quantidade": int(row["quantidade"] or 0),
                "total": valor,
                "percentual": _percentual(valor, total),
            }
        )
    top_fornecedores = [item for item in fornecedores if item["id"]][:LIMITE_TOP_FORNECEDORES]

    veiculos = []
    manutencoes = []
    if "financeiro.view_veiculo" in permissoes and quantidade:
        veiculos = _veiculos_e_categorias(pagas, total)
        manutencoes = _manutencao_por_veiculo(pagas)

    formas = []
    forma_rows = (
        pagas.exclude(forma_pagamento="")
        .values("forma_pagamento")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("-total")
    )
    mapa_formas = dict(ContaPagar.FORMA_CHOICES)
    for row in forma_rows:
        formas.append(
            {
                "nome": mapa_formas.get(row["forma_pagamento"], row["forma_pagamento"]),
                "quantidade": int(row["quantidade"] or 0),
                "total": _quantize(row["total"]),
            }
        )

    mensal = _mensal_consolidado(pagas, inicio, fim) if quantidade else []
    obrigacoes = _obrigacoes(params, permissoes, hoje)
    compromissos = _compromissos(params, hoje)

    categorias_filtro = list(
        CategoriaFinanceira.objects.filter(
            Q(ativo=True) | Q(contas_pagar__isnull=False)
        )
        .distinct()
        .order_by("ordem", "nome")
    )
    fornecedores_filtro = list(
        Fornecedor.objects.filter(Q(ativo=True) | Q(contas_pagar__isnull=False))
        .distinct()
        .order_by("nome")
    )
    veiculos_filtro = []
    if "financeiro.view_veiculo" in permissoes:
        veiculos_filtro = list(
            Veiculo.objects.filter(Q(ativo=True) | Q(contas_pagar__isnull=False))
            .distinct()
            .order_by("marca", "modelo")
        )

    filtros = {
        "categoria": (params.get("categoria") or "").strip(),
        "fornecedor": (params.get("fornecedor") or "").strip(),
        "veiculo": (params.get("veiculo") or "").strip(),
        "forma": (params.get("forma") or "").strip(),
        "exercicio": (params.get("exercicio") or "").strip(),
        "tipo": (params.get("tipo") or "").strip(),
        "status_obrigacao": (params.get("status_obrigacao") or "").strip(),
    }
    return RelatorioFinanceiro(
        periodo=chave,
        inicio=inicio,
        fim=fim,
        anterior_inicio=ant_inicio,
        anterior_fim=ant_fim,
        filtros=filtros,
        quantidade=quantidade,
        total=total,
        media=media,
        maior=maior,
        menor=menor,
        comparacao_atual=total,
        comparacao_anterior=total_anterior,
        comparacao_diferenca=total - total_anterior,
        comparacao_percentual=_variacao(total, total_anterior),
        categorias=categorias,
        chart_categorias=chart_categorias,
        evolucao=evolucao,
        chart_evolucao=chart_evolucao,
        fornecedores=fornecedores,
        top_fornecedores=top_fornecedores,
        veiculos=veiculos,
        manutencoes=manutencoes,
        formas=formas,
        mensal=mensal,
        obrigacoes=obrigacoes,
        compromissos=compromissos,
        categorias_filtro=categorias_filtro,
        fornecedores_filtro=fornecedores_filtro,
        veiculos_filtro=veiculos_filtro,
    )
