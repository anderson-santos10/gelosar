from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from accounts.authz import ModulePermissionRequiredMixin
from clientes.models import Cliente
from core.periodo import dia_local_atual

from .forms import ContaReceberForm
from .models import CategoriaFinanceira, ContaReceber
from .views import (
    FILTRO_SEM,
    _parametro,
    _parse_date,
    contar_filtros_ativos,
    requisicao_lista_parcial,
)

FILTRO_COM = "com"
FORMAS_RECEBIMENTO_VALIDAS = {
    codigo for codigo, _rotulo in ContaReceber.FORMA_CHOICES
}


def filtros_contas_receber(params):
    return {
        "q": _parametro(params, "q"),
        "status": _parametro(params, "status"),
        "categoria": _parametro(params, "categoria"),
        "cliente": _parametro(params, "cliente"),
        "competencia_inicio": _parametro(params, "competencia_inicio"),
        "competencia_fim": _parametro(params, "competencia_fim"),
        "vencimento_inicio": _parametro(params, "vencimento_inicio"),
        "vencimento_fim": _parametro(params, "vencimento_fim"),
        "forma_recebimento": _parametro(params, "forma_recebimento"),
        "venda": _parametro(params, "venda"),
    }


def filtrar_contas_receber(queryset, params):
    status = _parametro(params, "status")
    hoje = dia_local_atual()
    if status == ContaReceber.STATUS_PENDENTE:
        queryset = queryset.filter(
            status=ContaReceber.STATUS_PENDENTE,
            data_vencimento__gte=hoje,
        )
    elif status == "vencida":
        queryset = queryset.filter(
            status=ContaReceber.STATUS_PENDENTE,
            data_vencimento__lt=hoje,
        )
    elif status in {
        ContaReceber.STATUS_RECEBIDA,
        ContaReceber.STATUS_CANCELADA,
    }:
        queryset = queryset.filter(status=status)

    categoria = _parametro(params, "categoria")
    if categoria.isdigit():
        queryset = queryset.filter(
            categoria_id=int(categoria),
            categoria__tipo=CategoriaFinanceira.TIPO_RECEITA,
        )

    cliente = _parametro(params, "cliente")
    if cliente.isdigit():
        queryset = queryset.filter(cliente_id=int(cliente))

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

    forma = _parametro(params, "forma_recebimento")
    if forma in FORMAS_RECEBIMENTO_VALIDAS:
        queryset = queryset.filter(forma_recebimento=forma)

    venda = _parametro(params, "venda")
    if venda == FILTRO_SEM:
        queryset = queryset.filter(venda__isnull=True)
    elif venda == FILTRO_COM:
        queryset = queryset.filter(venda__isnull=False)
    elif venda.isdigit():
        queryset = queryset.filter(venda_id=int(venda))

    busca = _parametro(params, "q")
    if busca:
        queryset = queryset.filter(
            Q(descricao__icontains=busca)
            | Q(cliente__nome__icontains=busca)
            | Q(observacoes__icontains=busca)
        )
    return queryset


def totais_contas_receber(queryset):
    zero = Value(
        Decimal("0.00"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    hoje = dia_local_atual()
    return queryset.aggregate(
        total_geral=Coalesce(Sum("valor"), zero),
        total_pendente=Coalesce(
            Sum("valor", filter=Q(status=ContaReceber.STATUS_PENDENTE)),
            zero,
        ),
        total_a_receber=Coalesce(
            Sum(
                "valor",
                filter=Q(
                    status=ContaReceber.STATUS_PENDENTE,
                    data_vencimento__gte=hoje,
                ),
            ),
            zero,
        ),
        total_vencido=Coalesce(
            Sum(
                "valor",
                filter=Q(
                    status=ContaReceber.STATUS_PENDENTE,
                    data_vencimento__lt=hoje,
                ),
            ),
            zero,
        ),
        total_recebido=Coalesce(
            Sum("valor", filter=Q(status=ContaReceber.STATUS_RECEBIDA)),
            zero,
        ),
        total_cancelado=Coalesce(
            Sum("valor", filter=Q(status=ContaReceber.STATUS_CANCELADA)),
            zero,
        ),
    )


class ListaContasReceberView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, ListView
):
    permission_required = "financeiro.view_contareceber"
    model = ContaReceber
    template_name = "financeiro/lista_contas_receber.html"
    context_object_name = "contas"
    paginate_by = 25

    def get_template_names(self):
        if requisicao_lista_parcial(self.request):
            return ["financeiro/lista_contas_receber_resultados.html"]
        return [self.template_name]

    def get_queryset(self):
        if not hasattr(self, "_contas_filtradas"):
            queryset = ContaReceber.objects.select_related(
                "cliente",
                "categoria",
                "venda",
            ).order_by("data_vencimento", "-id")
            self._contas_filtradas = filtrar_contas_receber(
                queryset, self.request.GET
            )
        return self._contas_filtradas

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        querystring = self.request.GET.copy()
        querystring.pop("page", None)
        context["filtro_querystring"] = querystring.urlencode()
        context["filtros"] = filtros_contas_receber(self.request.GET)
        context["filtros_ativos"] = contar_filtros_ativos(context["filtros"])
        context["existem_contas"] = ContaReceber.objects.exists()
        context["categorias_filtro"] = CategoriaFinanceira.objects.filter(
            tipo=CategoriaFinanceira.TIPO_RECEITA,
        ).order_by("ordem", "nome")
        context["clientes_filtro"] = Cliente.objects.all().order_by("nome")
        context["formas_recebimento"] = ContaReceber.FORMA_CHOICES
        context["totais"] = totais_contas_receber(self.get_queryset())
        return context


class CriarContaReceberView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView
):
    permission_required = "financeiro.add_contareceber"
    model = ContaReceber
    form_class = ContaReceberForm
    template_name = "financeiro/conta_receber_form.html"
    success_url = reverse_lazy("financeiro:lista_contas_receber")

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        messages.success(self.request, "Conta a receber salva.")
        return super().form_valid(form)


class EditarContaReceberView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView
):
    permission_required = "financeiro.change_contareceber"
    model = ContaReceber
    form_class = ContaReceberForm
    template_name = "financeiro/conta_receber_form.html"
    success_url = reverse_lazy("financeiro:lista_contas_receber")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.has_perm(
            self.permission_required
        ):
            conta = get_object_or_404(ContaReceber, pk=kwargs["pk"])
            if conta.lancamento_fechado:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Conta a receber atualizada.")
        return super().form_valid(form)


class MarcarContaRecebidaView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = "financeiro.change_contareceber"

    def post(self, request, pk):
        with transaction.atomic():
            conta = get_object_or_404(
                ContaReceber.objects.select_for_update(),
                pk=pk,
            )
            if conta.status != ContaReceber.STATUS_PENDENTE:
                if conta.status == ContaReceber.STATUS_RECEBIDA:
                    messages.error(request, "Esta conta já está recebida.")
                elif conta.status == ContaReceber.STATUS_CANCELADA:
                    messages.error(
                        request,
                        "Conta cancelada não pode ser marcada como recebida.",
                    )
                else:
                    messages.error(
                        request, "Esta conta não pode ser marcada como recebida."
                    )
                return redirect("financeiro:lista_contas_receber")
            conta.status = ContaReceber.STATUS_RECEBIDA
            conta.data_recebimento = dia_local_atual()
            try:
                conta.full_clean()
            except ValidationError:
                messages.error(
                    request, "Não foi possível marcar esta conta como recebida."
                )
                return redirect("financeiro:lista_contas_receber")
            conta.save(
                update_fields=["status", "data_recebimento", "atualizado_em"]
            )
        messages.success(request, "Conta marcada como recebida.")
        return redirect("financeiro:lista_contas_receber")


class CancelarContaReceberView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = "financeiro.change_contareceber"

    def post(self, request, pk):
        with transaction.atomic():
            conta = get_object_or_404(
                ContaReceber.objects.select_for_update(),
                pk=pk,
            )
            if conta.status != ContaReceber.STATUS_PENDENTE:
                if conta.status == ContaReceber.STATUS_RECEBIDA:
                    messages.error(request, "Conta recebida não pode ser cancelada.")
                elif conta.status == ContaReceber.STATUS_CANCELADA:
                    messages.error(request, "Esta conta já está cancelada.")
                else:
                    messages.error(request, "Esta conta não pode ser cancelada.")
                return redirect("financeiro:lista_contas_receber")
            conta.status = ContaReceber.STATUS_CANCELADA
            conta.data_recebimento = None
            try:
                conta.full_clean()
            except ValidationError:
                messages.error(request, "Não foi possível cancelar esta conta.")
                return redirect("financeiro:lista_contas_receber")
            conta.save(
                update_fields=["status", "data_recebimento", "atualizado_em"]
            )
        messages.success(request, "Conta cancelada.")
        return redirect("financeiro:lista_contas_receber")
