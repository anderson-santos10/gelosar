from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from accounts.authz import module_permission_required, usuario_pode_ver_pedido
from clientes.models import Cliente
from core.auditoria import atribuir_criado_por
from estoque.services import QuantidadeNaoInteira
from produtos.models import Produto

from .forms import ItemPedidoFormSet, PedidoForm
from .models import Pedido, Venda
from .services import PedidoNaoAberto, entregar_pedido


def _produtos_precos_json():
    return {
        str(produto.pk): format(produto.preco_venda, "f")
        for produto in Produto.objects.filter(ativo=True).only("id", "preco_venda")
    }


def _dados_para_pedido(post):
    """Completa endereço e cidade a partir do cliente quando a tela ainda não envia esses campos."""
    dados = post.copy()
    if (dados.get("endereco") or "").strip():
        return dados
    cliente_id = dados.get("cliente")
    if not cliente_id:
        return dados
    cliente = (
        Cliente.objects.filter(pk=cliente_id)
        .only("id", "endereco", "cidade")
        .first()
    )
    if cliente is None:
        return dados
    dados["endereco"] = cliente.endereco
    if not (dados.get("cidade") or "").strip():
        dados["cidade"] = cliente.cidade
    return dados


@module_permission_required("vendas.add_venda")
def nova_venda(request):
    if request.method == "POST":
        dados = _dados_para_pedido(request.POST)
        pedido_form = PedidoForm(dados)
        formset = None
        if pedido_form.is_valid():
            try:
                with transaction.atomic():
                    pedido = pedido_form.save(commit=False)
                    pedido.status = Pedido.STATUS_ABERTO
                    atribuir_criado_por(pedido, request.user)
                    pedido.save()
                    formset = ItemPedidoFormSet(dados, instance=pedido)
                    if not formset.is_valid():
                        raise _ItensPedidoInvalidos()
                    formset.save()
            except _ItensPedidoInvalidos:
                if formset is not None and not formset.non_form_errors():
                    messages.error(
                        request,
                        "Os itens do pedido são inválidos. "
                        "Corrija os produtos e as quantidades informados.",
                    )
            else:
                messages.success(
                    request,
                    f"Pedido #{pedido.pk} registrado com sucesso.",
                )
                return redirect("vendas:detalhe_pedido", pk=pedido.pk)
        else:
            for erro in pedido_form.errors.get("endereco", []):
                messages.error(request, erro)
            for erro in pedido_form.errors.get("cidade", []):
                messages.error(request, erro)
            formset = ItemPedidoFormSet(dados)
        if formset is None:
            formset = ItemPedidoFormSet(dados)
    else:
        pedido_form = PedidoForm()
        formset = ItemPedidoFormSet()

    return render(
        request,
        "nova_venda.html",
        {
            "venda_form": pedido_form,
            "formset": formset,
            "clientes_enderecos": _enderecos_clientes_ativos(),
            "produtos_precos_json": _produtos_precos_json(),
        },
    )


@module_permission_required("vendas.view_venda")
def detalhe_venda(request, pk):

    venda = get_object_or_404(
        Venda.objects.select_related("cliente", "pedido").prefetch_related(
            "itens__produto"
        ),
        pk=pk
    )

    return render(
        request,
        'detalhe_venda.html',
        {
            'venda': venda,
        }
    )


class _ItensPedidoInvalidos(Exception):
    pass


def _enderecos_clientes_ativos():
    return {
        str(cliente.pk): {
            "endereco": cliente.endereco,
            "cidade": cliente.cidade,
        }
        for cliente in Cliente.objects.filter(ativo=True).only(
            "id",
            "endereco",
            "cidade",
        )
    }


def _queryset_pedido():
    return Pedido.objects.select_related(
        "cliente",
        "criado_por",
        "entregue_por",
        "venda",
    ).prefetch_related("itens__produto")


def cadastrar_pedido(request):
    return redirect("vendas:novo_pedido")


@module_permission_required("vendas.view_pedido")
def pedidos_abertos(request):
    queryset = _queryset_pedido().filter(
        status=Pedido.STATUS_ABERTO
    ).order_by("criado_em", "id")
    page_obj = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "pedidos_abertos.html",
        {
            "pedidos": page_obj.object_list,
            "page_obj": page_obj,
        },
    )


@module_permission_required("vendas.view_pedido")
def historico_pedidos(request):
    queryset = _queryset_pedido().filter(
        status=Pedido.STATUS_ENTREGUE
    ).order_by("-entregue_em", "-id")
    page_obj = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "historico_pedidos.html",
        {
            "pedidos": page_obj.object_list,
            "page_obj": page_obj,
        },
    )


@login_required
def detalhe_pedido(request, pk):
    pedido = get_object_or_404(_queryset_pedido(), pk=pk)
    if not usuario_pode_ver_pedido(request.user, pedido):
        raise PermissionDenied
    return render(
        request,
        "detalhe_pedido.html",
        {"pedido": pedido},
    )


@module_permission_required("vendas.entregar_pedido")
def confirmar_entrega_pedido(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not Pedido.objects.filter(pk=pk).exists():
        raise Http404("Pedido não encontrado.")
    try:
        pedido = entregar_pedido(pk, request.user)
    except Pedido.DoesNotExist:
        raise Http404("Pedido não encontrado.")
    except PedidoNaoAberto as exc:
        messages.error(request, exc.mensagem)
        return redirect("vendas:detalhe_pedido", pk=pk)
    except QuantidadeNaoInteira as exc:
        messages.error(request, str(exc))
        return redirect("vendas:detalhe_pedido", pk=pk)
    messages.success(
        request,
        f"Pedido #{pedido.pk} entregue. Venda #{pedido.venda_id} criada.",
    )
    return redirect("vendas:detalhe_pedido", pk=pedido.pk)
