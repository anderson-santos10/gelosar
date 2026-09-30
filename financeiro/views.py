from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.text import get_valid_filename
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from accounts.authz import ModulePermissionRequiredMixin
from core.periodo import dia_local_atual

from .forms import (
    CategoriaFinanceiraForm,
    ContaPagarForm,
    ContaRecorrenteForm,
    FornecedorForm,
    GerarCompetenciaForm,
)
from .models import (
    CategoriaFinanceira,
    ContaPagar,
    ContaRecorrente,
    Fornecedor,
    ObrigacaoVeiculo,
    Veiculo,
)
from .services.dashboard import PERIODO_OPCOES, montar_dashboard
from .services.relatorios import montar_relatorio
from .services.recorrentes import gerar_competencia


class DashboardFinanceiroView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = "financeiro.view_contapagar"
    template_name = "financeiro/dashboard.html"

    def get(self, request):
        permissoes = set()
        if request.user.has_perm("financeiro.view_contarecorrente"):
            permissoes.add("financeiro.view_contarecorrente")
        if request.user.has_perm("financeiro.view_veiculo"):
            permissoes.add("financeiro.view_veiculo")
        dashboard = montar_dashboard(request.GET, permissoes=permissoes)
        return render(
            request,
            self.template_name,
            {
                "dashboard": dashboard,
                "periodo_opcoes": PERIODO_OPCOES,
            },
        )


class RelatoriosFinanceiroView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = "financeiro.view_contapagar"
    template_name = "financeiro/relatorios.html"

    def get(self, request):
        permissoes = set()
        if request.user.has_perm("financeiro.view_veiculo"):
            permissoes.add("financeiro.view_veiculo")
        if request.user.has_perm("financeiro.view_obrigacaoveiculo"):
            permissoes.add("financeiro.view_obrigacaoveiculo")
        relatorio = montar_relatorio(request.GET, permissoes=permissoes)
        return render(
            request,
            self.template_name,
            {
                "relatorio": relatorio,
                "periodo_opcoes": PERIODO_OPCOES,
                "formas_pagamento": ContaPagar.FORMA_CHOICES,
                "tipos_obrigacao": ObrigacaoVeiculo.TIPO_CHOICES,
                "status_obrigacao": ObrigacaoVeiculo.STATUS_CHOICES,
            },
        )


class ListaFornecedoresView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "financeiro.view_fornecedor"
    model = Fornecedor
    template_name = "financeiro/lista_fornecedores.html"
    context_object_name = "fornecedores"


class CriarFornecedorView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "financeiro.add_fornecedor"
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "financeiro/fornecedor_form.html"
    success_url = reverse_lazy("financeiro:lista_fornecedores")

    def form_valid(self, form):
        messages.success(self.request, "Fornecedor salvo.")
        return super().form_valid(form)


class EditarFornecedorView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "financeiro.change_fornecedor"
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "financeiro/fornecedor_form.html"
    success_url = reverse_lazy("financeiro:lista_fornecedores")

    def form_valid(self, form):
        messages.success(self.request, "Fornecedor atualizado.")
        return super().form_valid(form)


class AlternarAtivoFornecedorView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = "financeiro.change_fornecedor"

    def post(self, request, pk):
        fornecedor = get_object_or_404(Fornecedor, pk=pk)
        fornecedor.ativo = not fornecedor.ativo
        fornecedor.save(update_fields=["ativo"])
        if fornecedor.ativo:
            messages.success(request, "Fornecedor ativado.")
        else:
            messages.success(request, "Fornecedor desativado.")
        return redirect("financeiro:lista_fornecedores")


class ListaCategoriasView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "financeiro.view_categoriafinanceira"
    model = CategoriaFinanceira
    template_name = "financeiro/lista_categorias.html"
    context_object_name = "categorias"


class CriarCategoriaView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "financeiro.add_categoriafinanceira"
    model = CategoriaFinanceira
    form_class = CategoriaFinanceiraForm
    template_name = "financeiro/categoria_form.html"
    success_url = reverse_lazy("financeiro:lista_categorias")

    def form_valid(self, form):
        messages.success(self.request, "Categoria financeira salva.")
        return super().form_valid(form)


class EditarCategoriaView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "financeiro.change_categoriafinanceira"
    model = CategoriaFinanceira
    form_class = CategoriaFinanceiraForm
    template_name = "financeiro/categoria_form.html"
    success_url = reverse_lazy("financeiro:lista_categorias")

    def form_valid(self, form):
        messages.success(self.request, "Categoria financeira atualizada.")
        return super().form_valid(form)


class AlternarAtivoCategoriaView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = "financeiro.change_categoriafinanceira"

    def post(self, request, pk):
        categoria = get_object_or_404(CategoriaFinanceira, pk=pk)
        categoria.ativo = not categoria.ativo
        categoria.save(update_fields=["ativo"])
        if categoria.ativo:
            messages.success(request, "Categoria ativada.")
        else:
            messages.success(request, "Categoria desativada.")
        return redirect("financeiro:lista_categorias")


FILTRO_SEM = "sem"
FORMAS_PAGAMENTO_VALIDAS = {codigo for codigo, _rotulo in ContaPagar.FORMA_CHOICES}


def _parse_date(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parametro(params, chave):
    return (params.get(chave) or "").strip()


def filtros_contas_pagar(params):
    fornecedor = _parametro(params, "fornecedor")
    if not fornecedor and _parametro(params, "sem_fornecedor") == "1":
        fornecedor = FILTRO_SEM
    return {
        "q": _parametro(params, "q"),
        "status": _parametro(params, "status"),
        "categoria": _parametro(params, "categoria"),
        "fornecedor": fornecedor,
        "sem_fornecedor": "1" if fornecedor == FILTRO_SEM else "",
        "competencia_inicio": _parametro(params, "competencia_inicio"),
        "competencia_fim": _parametro(params, "competencia_fim"),
        "vencimento_inicio": _parametro(params, "vencimento_inicio"),
        "vencimento_fim": _parametro(params, "vencimento_fim"),
        "forma_pagamento": _parametro(params, "forma_pagamento"),
        "veiculo": _parametro(params, "veiculo"),
    }


def contar_filtros_ativos(filtros):
    return sum(
        1
        for chave, valor in filtros.items()
        if valor and chave != "sem_fornecedor"
    )


def requisicao_lista_parcial(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def filtrar_contas_pagar(queryset, params):
    status = _parametro(params, "status")
    hoje = dia_local_atual()
    if status == ContaPagar.STATUS_PENDENTE:
        queryset = queryset.filter(
            status=ContaPagar.STATUS_PENDENTE,
            data_vencimento__gte=hoje,
        )
    elif status == "vencida":
        queryset = queryset.filter(
            status=ContaPagar.STATUS_PENDENTE,
            data_vencimento__lt=hoje,
        )
    elif status in {ContaPagar.STATUS_PAGO, ContaPagar.STATUS_CANCELADO}:
        queryset = queryset.filter(status=status)

    categoria = _parametro(params, "categoria")
    if categoria.isdigit():
        queryset = queryset.filter(categoria_id=int(categoria))

    fornecedor = _parametro(params, "fornecedor")
    if fornecedor == FILTRO_SEM or (
        _parametro(params, "sem_fornecedor") == "1" and not fornecedor.isdigit()
    ):
        queryset = queryset.filter(fornecedor__isnull=True)
    elif fornecedor.isdigit():
        queryset = queryset.filter(fornecedor_id=int(fornecedor))

    competencia_inicio = _parse_date(params.get("competencia_inicio"))
    if competencia_inicio:
        queryset = queryset.filter(competencia__gte=competencia_inicio)

    competencia_fim = _parse_date(params.get("competencia_fim"))
    if competencia_fim:
        queryset = queryset.filter(competencia__lte=competencia_fim)

    vencimento_inicio = _parse_date(params.get("vencimento_inicio"))
    if vencimento_inicio:
        queryset = queryset.filter(data_vencimento__gte=vencimento_inicio)

    vencimento_fim = _parse_date(params.get("vencimento_fim"))
    if vencimento_fim:
        queryset = queryset.filter(data_vencimento__lte=vencimento_fim)

    forma = _parametro(params, "forma_pagamento")
    if forma in FORMAS_PAGAMENTO_VALIDAS:
        queryset = queryset.filter(forma_pagamento=forma)

    veiculo = _parametro(params, "veiculo")
    if veiculo == FILTRO_SEM:
        queryset = queryset.filter(veiculo__isnull=True)
    elif veiculo.isdigit():
        queryset = queryset.filter(veiculo_id=int(veiculo))

    busca = _parametro(params, "q")
    if busca:
        queryset = queryset.filter(
            Q(descricao__icontains=busca)
            | Q(fornecedor__nome__icontains=busca)
            | Q(observacoes__icontains=busca)
        )
    return queryset


def totais_contas_pagar(queryset):
    zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
    hoje = dia_local_atual()
    return queryset.aggregate(
        total_geral=Coalesce(Sum("valor"), zero),
        total_pendente=Coalesce(
            Sum("valor", filter=Q(status=ContaPagar.STATUS_PENDENTE)),
            zero,
        ),
        total_vencido=Coalesce(
            Sum(
                "valor",
                filter=Q(
                    status=ContaPagar.STATUS_PENDENTE,
                    data_vencimento__lt=hoje,
                ),
            ),
            zero,
        ),
        total_pago=Coalesce(
            Sum("valor", filter=Q(status=ContaPagar.STATUS_PAGO)),
            zero,
        ),
    )


class ListaContasPagarView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "financeiro.view_contapagar"
    model = ContaPagar
    template_name = "financeiro/lista_contas_pagar.html"
    context_object_name = "contas"
    paginate_by = 25

    def get_template_names(self):
        if requisicao_lista_parcial(self.request):
            return ["financeiro/lista_contas_pagar_resultados.html"]
        return [self.template_name]

    def get_queryset(self):
        if not hasattr(self, "_contas_filtradas"):
            queryset = (
                ContaPagar.objects.select_related(
                    "categoria", "fornecedor", "veiculo"
                ).order_by("data_vencimento", "-id")
            )
            self._contas_filtradas = filtrar_contas_pagar(queryset, self.request.GET)
        return self._contas_filtradas

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.request.GET.copy()
        filtros.pop("page", None)
        context["filtro_querystring"] = filtros.urlencode()
        context["filtros"] = filtros_contas_pagar(self.request.GET)
        context["filtros_ativos"] = contar_filtros_ativos(context["filtros"])
        context["existem_contas"] = ContaPagar.objects.exists()
        context["categorias_filtro"] = CategoriaFinanceira.objects.all().order_by(
            "ordem", "nome"
        )
        context["fornecedores_filtro"] = Fornecedor.objects.all().order_by("nome")
        context["veiculos_filtro"] = Veiculo.objects.all().order_by(
            "marca", "modelo", "placa"
        )
        context["formas_pagamento"] = ContaPagar.FORMA_CHOICES
        context["totais"] = totais_contas_pagar(self.get_queryset())
        return context


class CriarContaPagarView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "financeiro.add_contapagar"
    model = ContaPagar
    form_class = ContaPagarForm
    template_name = "financeiro/conta_pagar_form.html"
    success_url = reverse_lazy("financeiro:lista_contas_pagar")

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        messages.success(self.request, "Conta a pagar salva.")
        return super().form_valid(form)


class EditarContaPagarView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "financeiro.change_contapagar"
    model = ContaPagar
    form_class = ContaPagarForm
    template_name = "financeiro/conta_pagar_form.html"
    success_url = reverse_lazy("financeiro:lista_contas_pagar")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.has_perm(
            self.permission_required
        ):
            conta = get_object_or_404(ContaPagar, pk=kwargs["pk"])
            if conta.lancamento_fechado:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Conta a pagar atualizada.")
        return super().form_valid(form)


class MarcarContaPagaView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = "financeiro.change_contapagar"

    def post(self, request, pk):
        with transaction.atomic():
            conta = get_object_or_404(
                ContaPagar.objects.select_for_update(),
                pk=pk,
            )
            if conta.status != ContaPagar.STATUS_PENDENTE:
                if conta.status == ContaPagar.STATUS_PAGO:
                    messages.error(request, "Esta conta já está paga.")
                elif conta.status == ContaPagar.STATUS_CANCELADO:
                    messages.error(
                        request,
                        "Conta cancelada não pode ser marcada como paga.",
                    )
                else:
                    messages.error(request, "Esta conta não pode ser marcada como paga.")
                return redirect("financeiro:lista_contas_pagar")
            conta.status = ContaPagar.STATUS_PAGO
            conta.data_pagamento = dia_local_atual()
            try:
                conta.full_clean()
            except ValidationError:
                messages.error(request, "Não foi possível marcar esta conta como paga.")
                return redirect("financeiro:lista_contas_pagar")
            conta.save(update_fields=["status", "data_pagamento", "atualizado_em"])
        messages.success(request, "Conta marcada como paga.")
        return redirect("financeiro:lista_contas_pagar")


class CancelarContaPagarView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = "financeiro.change_contapagar"

    def post(self, request, pk):
        with transaction.atomic():
            conta = get_object_or_404(
                ContaPagar.objects.select_for_update(),
                pk=pk,
            )
            if conta.status != ContaPagar.STATUS_PENDENTE:
                if conta.status == ContaPagar.STATUS_PAGO:
                    messages.error(request, "Conta paga não pode ser cancelada.")
                elif conta.status == ContaPagar.STATUS_CANCELADO:
                    messages.error(request, "Esta conta já está cancelada.")
                else:
                    messages.error(request, "Esta conta não pode ser cancelada.")
                return redirect("financeiro:lista_contas_pagar")
            conta.status = ContaPagar.STATUS_CANCELADO
            conta.data_pagamento = None
            try:
                conta.full_clean()
            except ValidationError:
                messages.error(request, "Não foi possível cancelar esta conta.")
                return redirect("financeiro:lista_contas_pagar")
            conta.save(update_fields=["status", "data_pagamento", "atualizado_em"])
        messages.success(request, "Conta cancelada.")
        return redirect("financeiro:lista_contas_pagar")


class DownloadAnexoContaPagarView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = "financeiro.view_contapagar"

    def get(self, request, pk):
        conta = get_object_or_404(ContaPagar, pk=pk)
        arquivo = conta.anexo
        if not arquivo:
            raise Http404("Conta sem comprovante.")
        try:
            if not arquivo.storage.exists(arquivo.name):
                raise Http404("Arquivo não encontrado.")
            handle = arquivo.open("rb")
        except Http404:
            raise
        except Exception:
            raise Http404("Arquivo não encontrado.")

        nome_bruto = Path(arquivo.name).name.replace("\r", "").replace("\n", "")
        nome = get_valid_filename(nome_bruto) or "comprovante"
        response = FileResponse(
            handle,
            as_attachment=True,
            filename=nome,
            content_type="application/octet-stream",
        )
        response["Content-Type"] = "application/octet-stream"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ListaContasRecorrentesView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, ListView
):
    permission_required = "financeiro.view_contarecorrente"
    model = ContaRecorrente
    template_name = "financeiro/lista_contas_recorrentes.html"
    context_object_name = "recorrentes"

    def get_queryset(self):
        queryset = ContaRecorrente.objects.select_related(
            "categoria",
            "fornecedor",
        ).annotate(qtd_contas=Count("contas_geradas"))
        params = self.request.GET
        busca = (params.get("q") or "").strip()
        if busca:
            queryset = queryset.filter(descricao__icontains=busca)
        categoria = (params.get("categoria") or "").strip()
        if categoria.isdigit():
            queryset = queryset.filter(categoria_id=int(categoria))
        fornecedor = (params.get("fornecedor") or "").strip()
        if fornecedor.isdigit():
            queryset = queryset.filter(fornecedor_id=int(fornecedor))
        ativa = (params.get("ativa") or "").strip()
        if ativa == "1":
            queryset = queryset.filter(ativa=True)
        elif ativa == "0":
            queryset = queryset.filter(ativa=False)
        return queryset.order_by("descricao")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "categoria": self.request.GET.get("categoria", ""),
            "fornecedor": self.request.GET.get("fornecedor", ""),
            "ativa": self.request.GET.get("ativa", ""),
        }
        context["categorias_filtro"] = CategoriaFinanceira.objects.all().order_by(
            "ordem", "nome"
        )
        context["fornecedores_filtro"] = Fornecedor.objects.all().order_by("nome")
        return context


class CriarContaRecorrenteView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView
):
    permission_required = "financeiro.add_contarecorrente"
    model = ContaRecorrente
    form_class = ContaRecorrenteForm
    template_name = "financeiro/conta_recorrente_form.html"
    success_url = reverse_lazy("financeiro:lista_contas_recorrentes")

    def form_valid(self, form):
        messages.success(self.request, "Conta recorrente salva.")
        return super().form_valid(form)


class EditarContaRecorrenteView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView
):
    permission_required = "financeiro.change_contarecorrente"
    model = ContaRecorrente
    form_class = ContaRecorrenteForm
    template_name = "financeiro/conta_recorrente_form.html"
    success_url = reverse_lazy("financeiro:lista_contas_recorrentes")

    def form_valid(self, form):
        messages.success(self.request, "Conta recorrente atualizada.")
        return super().form_valid(form)


class AlternarAtivoContaRecorrenteView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = "financeiro.change_contarecorrente"

    def post(self, request, pk):
        recorrente = get_object_or_404(ContaRecorrente, pk=pk)
        recorrente.ativa = not recorrente.ativa
        recorrente.save(update_fields=["ativa"])
        if recorrente.ativa:
            messages.success(request, "Recorrência ativada.")
        else:
            messages.success(request, "Recorrência desativada. Contas já geradas foram preservadas.")
        return redirect("financeiro:lista_contas_recorrentes")


class GerarContasRecorrentesView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = (
        "financeiro.change_contarecorrente",
        "financeiro.add_contapagar",
    )
    template_name = "financeiro/gerar_contas_recorrentes.html"

    def get(self, request):
        hoje = dia_local_atual()
        form = GerarCompetenciaForm(initial={"mes": hoje.month, "ano": hoje.year})
        return render(request, self.template_name, {"form": form, "resumo": None})

    def post(self, request):
        form = GerarCompetenciaForm(request.POST)
        resumo = None
        if form.is_valid():
            resumo = gerar_competencia(
                form.cleaned_data["mes"],
                form.cleaned_data["ano"],
                criado_por=request.user,
            )
            messages.success(
                request,
                (
                    f"{resumo.criadas} contas criadas. "
                    f"{resumo.existentes} contas já existentes. "
                    f"{resumo.inativas} recorrências inativas. "
                    f"{resumo.fora_vigencia} fora da vigência. "
                    f"{len(resumo.erros)} com erro."
                ),
            )
        return render(request, self.template_name, {"form": form, "resumo": resumo})
