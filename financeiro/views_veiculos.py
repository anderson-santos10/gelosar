from decimal import Decimal
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.text import get_valid_filename
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.authz import ModulePermissionRequiredMixin
from core.periodo import dia_local_atual

from .forms import (
    GerarObrigacoesForm,
    ManutencaoVeiculoForm,
    ObrigacaoVeiculoForm,
    PlanoManutencaoForm,
    VeiculoForm,
)
from .models import (
    ContaPagar,
    ManutencaoVeiculo,
    ObrigacaoVeiculo,
    PlanoManutencao,
    Veiculo,
)
from .services.ipva import avaliar_ipva
from .services.manutencao import (
    SITUACAO_ATRASADA,
    SITUACAO_PROXIMA,
    resumo_manutencao_veiculo,
    situacoes_do_veiculo,
)
from .services.obrigacoes_veiculo import (
    gerar_obrigacoes_exercicio,
    gerar_obrigacoes_frota,
)


def _badge_manutencao(situacao):
    mapa = {
        "atrasada": "gs-badge--danger",
        "proxima": "gs-badge--warning",
        "em_dia": "gs-badge--ok",
        "sem_historico": "gs-badge--neutral",
        "inativo": "gs-badge--neutral",
    }
    return mapa.get(situacao, "gs-badge--neutral")


def _badge_obrigacao(obrigacao, hoje=None):
    hoje = hoje or dia_local_atual()
    if obrigacao.status == ObrigacaoVeiculo.STATUS_PAGO:
        return "Pago", "gs-badge--ok"
    if obrigacao.status == ObrigacaoVeiculo.STATUS_ISENTO:
        return "Isento", "gs-badge--ok"
    if obrigacao.status == ObrigacaoVeiculo.STATUS_NAO_APLICAVEL:
        return "Não aplicável", "gs-badge--neutral"
    if obrigacao.status == ObrigacaoVeiculo.STATUS_CANCELADO:
        return "Cancelado", "gs-badge--neutral"
    if obrigacao.data_vencimento and obrigacao.data_vencimento < hoje:
        return "Atrasado", "gs-badge--danger"
    if not obrigacao.data_vencimento:
        return "Não informado", "gs-badge--neutral"
    return "Pendente", "gs-badge--warning"


def filtrar_veiculos(queryset, params):
    ativo = (params.get("ativo") or "").strip()
    if ativo == "1":
        queryset = queryset.filter(ativo=True)
    elif ativo == "0":
        queryset = queryset.filter(ativo=False)
    marca = (params.get("marca") or "").strip()
    if marca:
        queryset = queryset.filter(marca__icontains=marca)
    modelo = (params.get("modelo") or "").strip()
    if modelo:
        queryset = queryset.filter(modelo__icontains=modelo)
    placa = (params.get("placa") or "").strip()
    if placa:
        queryset = queryset.filter(placa__icontains=placa.replace("-", "").replace(" ", ""))
    busca = (params.get("q") or "").strip()
    if busca:
        queryset = queryset.filter(
            Q(marca__icontains=busca)
            | Q(modelo__icontains=busca)
            | Q(placa__icontains=busca.replace("-", "").replace(" ", ""))
            | Q(versao__icontains=busca)
        )
    return queryset


def proxima_obrigacao(obrigacoes, hoje=None):
    hoje = hoje or dia_local_atual()
    pendentes = [
        item
        for item in obrigacoes
        if item.status == ObrigacaoVeiculo.STATUS_PENDENTE
    ]
    if not pendentes:
        return None
    com_data = [item for item in pendentes if item.data_vencimento]
    if com_data:
        return min(com_data, key=lambda item: item.data_vencimento)
    return pendentes[0]


class ListaVeiculosView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "financeiro.view_veiculo"
    model = Veiculo
    template_name = "financeiro/lista_veiculos.html"
    context_object_name = "veiculos"
    paginate_by = 25

    def get_queryset(self):
        queryset = Veiculo.objects.prefetch_related(
            Prefetch("planos", queryset=PlanoManutencao.objects.order_by("nome")),
            Prefetch(
                "manutencoes",
                queryset=ManutencaoVeiculo.objects.order_by(
                    "-data_realizacao", "-km_realizacao"
                ),
            ),
            Prefetch(
                "obrigacoes",
                queryset=ObrigacaoVeiculo.objects.order_by("-exercicio", "tipo"),
            ),
        )
        return filtrar_veiculos(queryset, self.request.GET).order_by(
            "marca", "modelo", "placa"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = dia_local_atual()
        linhas = []
        for veiculo in context["veiculos"]:
            situacoes = situacoes_do_veiculo(
                veiculo,
                planos=list(veiculo.planos.all()),
                historico=list(veiculo.manutencoes.all()),
                hoje=hoje,
            )
            codigo, rotulo = resumo_manutencao_veiculo(situacoes)
            obrigacao = proxima_obrigacao(list(veiculo.obrigacoes.all()), hoje=hoje)
            linhas.append(
                {
                    "veiculo": veiculo,
                    "manutencao_codigo": codigo,
                    "manutencao_rotulo": rotulo,
                    "manutencao_badge": _badge_manutencao(codigo),
                    "proxima_obrigacao": obrigacao,
                }
            )
        filtros = self.request.GET.copy()
        filtros.pop("page", None)
        context["linhas"] = linhas
        context["filtro_querystring"] = filtros.urlencode()
        context["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "marca": self.request.GET.get("marca", ""),
            "modelo": self.request.GET.get("modelo", ""),
            "placa": self.request.GET.get("placa", ""),
            "ativo": self.request.GET.get("ativo", ""),
        }
        return context


class CriarVeiculoView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):
    permission_required = "financeiro.add_veiculo"
    model = Veiculo
    form_class = VeiculoForm
    template_name = "financeiro/veiculo_form.html"
    success_url = reverse_lazy("financeiro:lista_veiculos")

    def form_valid(self, form):
        messages.success(self.request, "Veículo salvo.")
        return super().form_valid(form)


class EditarVeiculoView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):
    permission_required = "financeiro.change_veiculo"
    model = Veiculo
    form_class = VeiculoForm
    template_name = "financeiro/veiculo_form.html"

    def get_success_url(self):
        return reverse("financeiro:detalhe_veiculo", args=[self.object.pk])

    def form_valid(self, form):
        messages.success(self.request, "Veículo atualizado.")
        return super().form_valid(form)


class AlternarAtivoVeiculoView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = "financeiro.change_veiculo"

    def post(self, request, pk):
        veiculo = get_object_or_404(Veiculo, pk=pk)
        veiculo.ativo = not veiculo.ativo
        veiculo.save(update_fields=["ativo", "atualizado_em"])
        if veiculo.ativo:
            messages.success(request, "Veículo ativado.")
        else:
            messages.success(request, "Veículo inativado.")
        return redirect("financeiro:lista_veiculos")


class DetalheVeiculoView(LoginRequiredMixin, ModulePermissionRequiredMixin, DetailView):
    permission_required = "financeiro.view_veiculo"
    model = Veiculo
    template_name = "financeiro/detalhe_veiculo.html"
    context_object_name = "veiculo"

    def get_queryset(self):
        return Veiculo.objects.prefetch_related(
            Prefetch("planos", queryset=PlanoManutencao.objects.order_by("nome")),
            Prefetch(
                "manutencoes",
                queryset=ManutencaoVeiculo.objects.select_related("plano", "fornecedor"),
            ),
            Prefetch(
                "obrigacoes",
                queryset=ObrigacaoVeiculo.objects.order_by("-exercicio", "tipo"),
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        veiculo = self.object
        hoje = dia_local_atual()
        historico = list(veiculo.manutencoes.all())
        planos = list(veiculo.planos.all())
        situacoes = situacoes_do_veiculo(
            veiculo, planos=planos, historico=historico, hoje=hoje
        )
        atrasadas = [item for item in situacoes if item.situacao == SITUACAO_ATRASADA]
        proximas = [item for item in situacoes if item.situacao == SITUACAO_PROXIMA]
        exercicio = hoje.year
        situacao_ipva = avaliar_ipva(veiculo, exercicio)
        obrigacoes = list(veiculo.obrigacoes.all())
        licenciamento = next(
            (
                item
                for item in obrigacoes
                if item.tipo == ObrigacaoVeiculo.TIPO_LICENCIAMENTO
                and item.exercicio == exercicio
            ),
            None,
        )
        lic_rotulo, lic_badge = (
            _badge_obrigacao(licenciamento, hoje)
            if licenciamento
            else ("Não informado", "gs-badge--neutral")
        )
        zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
        contas = (
            ContaPagar.objects.filter(veiculo=veiculo)
            .exclude(status=ContaPagar.STATUS_CANCELADO)
            .select_related("categoria", "fornecedor")
            .order_by("-competencia", "-id")
        )
        inicio_ano = hoje.replace(month=1, day=1)
        custo_ano = contas.filter(competencia__gte=inicio_ano).aggregate(
            total=Coalesce(Sum("valor"), zero)
        )["total"]
        context.update(
            {
                "situacoes": situacoes,
                "atrasadas_count": len(atrasadas),
                "proximas_count": len(proximas),
                "situacao_ipva": situacao_ipva,
                "licenciamento": licenciamento,
                "licenciamento_rotulo": lic_rotulo,
                "licenciamento_badge": lic_badge,
                "obrigacoes": obrigacoes,
                "contas": contas[:20],
                "custo_ano": custo_ano,
                "exercicio": exercicio,
                "planos_ativos": [plano for plano in planos if plano.ativo],
            }
        )
        return context


class ListaPlanosVeiculoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, ListView
):
    permission_required = "financeiro.view_planomanutencao"
    template_name = "financeiro/lista_planos_veiculo.html"
    context_object_name = "situacoes"

    def dispatch(self, request, *args, **kwargs):
        self.veiculo = get_object_or_404(Veiculo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        planos = list(self.veiculo.planos.order_by("nome"))
        historico = list(self.veiculo.manutencoes.all())
        return situacoes_do_veiculo(self.veiculo, planos=planos, historico=historico)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["veiculo"] = self.veiculo
        return context


class CriarPlanoVeiculoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView
):
    permission_required = "financeiro.add_planomanutencao"
    model = PlanoManutencao
    form_class = PlanoManutencaoForm
    template_name = "financeiro/plano_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.veiculo = get_object_or_404(Veiculo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = kwargs.get("instance") or PlanoManutencao(
            veiculo=self.veiculo
        )
        return kwargs

    def form_valid(self, form):
        form.instance.veiculo = self.veiculo
        messages.success(self.request, "Plano de manutenção salvo.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("financeiro:lista_planos_veiculo", args=[self.veiculo.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["veiculo"] = self.veiculo
        return context


class EditarPlanoVeiculoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView
):
    permission_required = "financeiro.change_planomanutencao"
    model = PlanoManutencao
    form_class = PlanoManutencaoForm
    template_name = "financeiro/plano_form.html"
    pk_url_kwarg = "plano_pk"

    def dispatch(self, request, *args, **kwargs):
        self.veiculo = get_object_or_404(Veiculo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return PlanoManutencao.objects.filter(veiculo=self.veiculo)

    def form_valid(self, form):
        messages.success(self.request, "Plano de manutenção atualizado.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("financeiro:lista_planos_veiculo", args=[self.veiculo.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["veiculo"] = self.veiculo
        return context


class AlternarAtivoPlanoView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = "financeiro.change_planomanutencao"

    def post(self, request, pk, plano_pk):
        plano = get_object_or_404(PlanoManutencao, pk=plano_pk, veiculo_id=pk)
        plano.ativo = not plano.ativo
        plano.save(update_fields=["ativo", "atualizado_em"])
        if plano.ativo:
            messages.success(request, "Plano ativado.")
        else:
            messages.success(request, "Plano desativado. O histórico foi preservado.")
        return redirect("financeiro:lista_planos_veiculo", pk=pk)


class ListaManutencoesVeiculoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, ListView
):
    permission_required = "financeiro.view_manutencaoveiculo"
    template_name = "financeiro/lista_manutencoes.html"
    context_object_name = "manutencoes"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        self.veiculo = get_object_or_404(Veiculo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            ManutencaoVeiculo.objects.filter(veiculo=self.veiculo)
            .select_related("plano", "fornecedor")
            .order_by("-data_realizacao", "-km_realizacao")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["veiculo"] = self.veiculo
        return context


class CriarManutencaoVeiculoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView
):
    permission_required = "financeiro.add_manutencaoveiculo"
    model = ManutencaoVeiculo
    form_class = ManutencaoVeiculoForm
    template_name = "financeiro/manutencao_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.veiculo = get_object_or_404(Veiculo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["veiculo"] = self.veiculo
        kwargs["instance"] = kwargs.get("instance") or ManutencaoVeiculo(
            veiculo=self.veiculo
        )
        return kwargs

    def form_valid(self, form):
        form.instance.veiculo = self.veiculo
        form.instance.criado_por = self.request.user
        messages.success(self.request, "Manutenção registrada.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "financeiro:detalhe_manutencao",
            args=[self.veiculo.pk, self.object.pk],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["veiculo"] = self.veiculo
        return context


class EditarManutencaoVeiculoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView
):
    permission_required = "financeiro.change_manutencaoveiculo"
    model = ManutencaoVeiculo
    form_class = ManutencaoVeiculoForm
    template_name = "financeiro/manutencao_form.html"
    pk_url_kwarg = "manutencao_pk"

    def dispatch(self, request, *args, **kwargs):
        self.veiculo = get_object_or_404(Veiculo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return ManutencaoVeiculo.objects.filter(veiculo=self.veiculo)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["veiculo"] = self.veiculo
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Manutenção atualizada.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "financeiro:detalhe_manutencao",
            args=[self.veiculo.pk, self.object.pk],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["veiculo"] = self.veiculo
        return context


class DetalheManutencaoVeiculoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, DetailView
):
    permission_required = "financeiro.view_manutencaoveiculo"
    model = ManutencaoVeiculo
    template_name = "financeiro/detalhe_manutencao.html"
    context_object_name = "manutencao"
    pk_url_kwarg = "manutencao_pk"

    def dispatch(self, request, *args, **kwargs):
        self.veiculo = get_object_or_404(Veiculo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return ManutencaoVeiculo.objects.filter(veiculo=self.veiculo).select_related(
            "plano", "fornecedor", "veiculo"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contas = (
            self.object.contas_pagar.select_related("categoria", "fornecedor")
            .order_by("data_vencimento", "id")
        )
        context["veiculo"] = self.veiculo
        context["contas"] = contas
        context["custo_financeiro"] = self.object.custo_financeiro()
        return context


class DownloadAnexoManutencaoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, View
):
    permission_required = "financeiro.view_manutencaoveiculo"

    def get(self, request, pk, manutencao_pk):
        manutencao = get_object_or_404(
            ManutencaoVeiculo, pk=manutencao_pk, veiculo_id=pk
        )
        arquivo = manutencao.anexo
        if not arquivo:
            raise Http404("Manutenção sem anexo.")
        try:
            if not arquivo.storage.exists(arquivo.name):
                raise Http404("Arquivo não encontrado.")
            handle = arquivo.open("rb")
        except Http404:
            raise
        except Exception:
            raise Http404("Arquivo não encontrado.")
        nome_bruto = Path(arquivo.name).name.replace("\r", "").replace("\n", "")
        nome = get_valid_filename(nome_bruto) or "anexo"
        response = FileResponse(
            handle,
            as_attachment=True,
            filename=nome,
            content_type="application/octet-stream",
        )
        response["Content-Type"] = "application/octet-stream"
        response["X-Content-Type-Options"] = "nosniff"
        return response


def filtrar_obrigacoes(queryset, params):
    veiculo = (params.get("veiculo") or "").strip()
    if veiculo.isdigit():
        queryset = queryset.filter(veiculo_id=int(veiculo))
    tipo = (params.get("tipo") or "").strip()
    if tipo:
        queryset = queryset.filter(tipo=tipo)
    exercicio = (params.get("exercicio") or "").strip()
    if exercicio.isdigit():
        queryset = queryset.filter(exercicio=int(exercicio))
    status = (params.get("status") or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    return queryset


class ListaObrigacoesView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):
    permission_required = "financeiro.view_obrigacaoveiculo"
    model = ObrigacaoVeiculo
    template_name = "financeiro/lista_obrigacoes.html"
    context_object_name = "obrigacoes"
    paginate_by = 25

    def get_queryset(self):
        queryset = ObrigacaoVeiculo.objects.select_related("veiculo")
        return filtrar_obrigacoes(queryset, self.request.GET).order_by(
            "-exercicio", "tipo", "veiculo__marca"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = dia_local_atual()
        linhas = []
        for obrigacao in context["obrigacoes"]:
            rotulo, badge = _badge_obrigacao(obrigacao, hoje)
            linhas.append(
                {"obrigacao": obrigacao, "rotulo": rotulo, "badge": badge}
            )
        filtros = self.request.GET.copy()
        filtros.pop("page", None)
        context["linhas"] = linhas
        context["filtro_querystring"] = filtros.urlencode()
        context["filtros"] = {
            "veiculo": self.request.GET.get("veiculo", ""),
            "tipo": self.request.GET.get("tipo", ""),
            "exercicio": self.request.GET.get("exercicio", ""),
            "status": self.request.GET.get("status", ""),
        }
        context["veiculos_filtro"] = Veiculo.objects.order_by("marca", "modelo")
        context["tipos"] = ObrigacaoVeiculo.TIPO_CHOICES
        context["status_choices"] = ObrigacaoVeiculo.STATUS_CHOICES
        return context


class DetalheObrigacaoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, DetailView
):
    permission_required = "financeiro.view_obrigacaoveiculo"
    model = ObrigacaoVeiculo
    template_name = "financeiro/detalhe_obrigacao.html"
    context_object_name = "obrigacao"

    def get_queryset(self):
        return ObrigacaoVeiculo.objects.select_related("veiculo")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contas = self.object.contas_pagar.select_related(
            "categoria", "fornecedor"
        ).order_by("data_vencimento")
        rotulo, badge = _badge_obrigacao(self.object)
        context["contas"] = contas
        context["rotulo"] = rotulo
        context["badge"] = badge
        if self.object.tipo == ObrigacaoVeiculo.TIPO_IPVA:
            context["situacao_ipva"] = avaliar_ipva(
                self.object.veiculo, self.object.exercicio
            )
        return context


class EditarObrigacaoView(
    LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView
):
    permission_required = "financeiro.change_obrigacaoveiculo"
    model = ObrigacaoVeiculo
    form_class = ObrigacaoVeiculoForm
    template_name = "financeiro/obrigacao_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["veiculo"] = self.object.veiculo
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Obrigação atualizada.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("financeiro:detalhe_obrigacao", args=[self.object.pk])


class GerarObrigacoesView(LoginRequiredMixin, ModulePermissionRequiredMixin, View):
    permission_required = (
        "financeiro.add_obrigacaoveiculo",
        "financeiro.change_obrigacaoveiculo",
    )
    template_name = "financeiro/gerar_obrigacoes.html"

    def get(self, request):
        hoje = dia_local_atual()
        form = GerarObrigacoesForm(initial={"exercicio": hoje.year})
        return render(request, self.template_name, {"form": form, "resumo": None})

    def post(self, request):
        form = GerarObrigacoesForm(request.POST)
        resumo = None
        if form.is_valid():
            exercicio = form.cleaned_data["exercicio"]
            veiculo = form.cleaned_data.get("veiculo")
            if veiculo:
                resumo = gerar_obrigacoes_exercicio(veiculo, exercicio)
            else:
                resumo = gerar_obrigacoes_frota(exercicio)
            messages.success(
                request,
                (
                    f"{resumo.criadas} obrigações criadas. "
                    f"{resumo.atualizadas} atualizadas. "
                    f"{resumo.preservadas} já existentes preservadas. "
                    "Nenhuma conta a pagar foi gerada automaticamente."
                ),
            )
        return render(request, self.template_name, {"form": form, "resumo": resumo})
