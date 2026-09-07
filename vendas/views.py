from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from estoque.services import QuantidadeNaoInteira, registrar_saidas_venda
from produtos.models import Produto

from .forms import VendaForm, ItemVendaFormSet
from .models import Venda


def _produtos_precos_json():
    return {
        str(produto.pk): format(produto.preco_venda, "f")
        for produto in Produto.objects.filter(ativo=True).only("id", "preco_venda")
    }


class _ItensVendaInvalidos(Exception):
    pass


@login_required
def nova_venda(request):

    if request.method == 'POST':

        venda_form = VendaForm(request.POST)

        if venda_form.is_valid():

            formset = None

            try:
                with transaction.atomic():
                    venda = venda_form.save()
                    formset = ItemVendaFormSet(
                        request.POST,
                        instance=venda
                    )
                    if not formset.is_valid():
                        raise _ItensVendaInvalidos()
                    formset.save()
                    registrar_saidas_venda(venda)
            except (_ItensVendaInvalidos, QuantidadeNaoInteira):
                pass
            else:
                messages.success(
                    request,
                    f'Pedido #{venda.id} criado com sucesso!'
                )
                return redirect(
                    'vendas:detalhe_venda',
                    pk=venda.pk
                )

        else:

            formset = ItemVendaFormSet(request.POST)

    else:

        venda_form = VendaForm()
        formset = ItemVendaFormSet()

    return render(
        request,
        'nova_venda.html',
        {
            'venda_form': venda_form,
            'formset': formset,
            'produtos_precos_json': _produtos_precos_json(),
        }
    )


@login_required
def detalhe_venda(request, pk):

    venda = get_object_or_404(
        Venda,
        pk=pk
    )

    return render(
        request,
        'detalhe_venda.html',
        {
            'venda': venda,
        }
    )
