from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView, CreateView, UpdateView
from django.urls import reverse, reverse_lazy

from accounts.authz import ModulePermissionRequiredMixin
from core.charts import compras_cliente_por_mes, mix_produtos_cliente

from .models import Cliente


CAMPOS_CLIENTE = [
    'nome',
    'cnpj',
    'telefone',
    'email',
    'endereco',
    'cidade',
    'ativo',
    'observacoes',
]


class CriarClienteView(LoginRequiredMixin, ModulePermissionRequiredMixin, CreateView):

    permission_required = "clientes.add_cliente"

    model = Cliente
    template_name = 'cliente/cliente_form.html'
    fields = CAMPOS_CLIENTE
    success_url = reverse_lazy('clientes:lista_clientes')


class ListaClientesView(LoginRequiredMixin, ModulePermissionRequiredMixin, ListView):

    permission_required = "clientes.view_cliente"

    model = Cliente

    template_name = 'cliente/lista_clientes.html'

    context_object_name = 'clientes'


class EditarClienteView(LoginRequiredMixin, ModulePermissionRequiredMixin, UpdateView):

    permission_required = "clientes.change_cliente"

    model = Cliente
    template_name = 'cliente/cliente_form.html'
    fields = CAMPOS_CLIENTE

    def get_success_url(self):
        return reverse('clientes:dashboard_cliente', args=[self.object.pk])


class DashboardClienteView(LoginRequiredMixin, ModulePermissionRequiredMixin, DetailView):

    permission_required = "clientes.view_cliente"

    model = Cliente

    template_name = 'cliente/dashboard_cliente.html'

    context_object_name = 'cliente'

    def get_queryset(self):

        return Cliente.objects.prefetch_related(
            'vendas__itens__produto',
            'equipamentos'
        )

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        cliente = self.object

        # =====================================================
        # VENDAS DO CLIENTE
        # =====================================================

        vendas = cliente.vendas.all()

        # =====================================================
        # TOTAL COMPRADO PELO CLIENTE
        # =====================================================

        total_compras = sum(
            venda.total
            for venda in vendas
        )

        # =====================================================
        # QUANTIDADE TOTAL DE SACOS
        # =====================================================

        quantidade_total = sum(
            venda.quantidade_total
            for venda in vendas
        )

        # =====================================================
        # ÚLTIMA COMPRA
        # =====================================================

        ultima_compra = vendas.first()

        # =====================================================
        # EQUIPAMENTOS ALOCADOS
        # =====================================================

        equipamentos = cliente.equipamentos.all()

        # MÉTRICA GERENCIAL (não é regra de comodato):
        # compara o total comprado com o valor de aquisição dos equipamentos.

        valor_investimento = sum(
            equipamento.valor_compra or 0
            for equipamento in equipamentos
        )

        # =====================================================
        # VALOR JÁ RECUPERADO
        # =====================================================

        valor_recuperado = total_compras

        # =====================================================
        # VALOR RESTANTE
        # =====================================================

        valor_restante = valor_investimento - valor_recuperado

        # Evita valor negativo caso o cliente já tenha
        # comprado mais do que o valor do investimento.

        if valor_restante < 0:
            valor_restante = 0

        # =====================================================
        # PERCENTUAL DE RECUPERAÇÃO
        # =====================================================

        if valor_investimento > 0:

            percentual_recuperado = (
                valor_recuperado / valor_investimento
            ) * 100

            # Limita a barra em 100%

            if percentual_recuperado > 100:
                percentual_recuperado = 100

        else:

            percentual_recuperado = 0

        # =====================================================
        # PRODUTOS COMPRADOS
        # =====================================================

        produtos = {}

        for venda in vendas:

            for item in venda.itens.all():

                nome = item.produto.nome

                if nome not in produtos:
                    produtos[nome] = 0

                produtos[nome] += item.quantidade

        # =====================================================
        # CONTEXTO
        # =====================================================

        context.update({

            'vendas': vendas,

            'total_compras': total_compras,

            'quantidade_total': quantidade_total,

            'ultima_compra': ultima_compra,

            'equipamentos': equipamentos,

            'produtos': produtos,

            # Dados do investimento

            'valor_investimento': valor_investimento,

            'valor_recuperado': valor_recuperado,

            'valor_restante': valor_restante,

            'percentual_recuperado': percentual_recuperado,

            'chart_compras_mes': compras_cliente_por_mes(cliente),
            'chart_produtos': mix_produtos_cliente(produtos),

        })

        return context

