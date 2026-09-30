from decimal import Decimal

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from clientes.models import Cliente
from produtos.models import Produto

from .models import ItemPedido, ItemVenda, Pedido, Venda


class VendaForm(forms.ModelForm):

    class Meta:
        model = Venda
        fields = ['cliente', 'observacoes']

        widgets = {
            'cliente': forms.Select(attrs={
                'class': 'form-control gs-input'
            }),

            'observacoes': forms.Textarea(attrs={
                'class': 'form-control gs-input',
                'rows': 3,
                'placeholder': 'Observações da venda...'
            }),
        }


class ItemVendaForm(forms.ModelForm):

    class Meta:
        model = ItemVenda
        fields = ['produto', 'quantidade']

        widgets = {
            'produto': forms.Select(attrs={
                'class': 'form-control gs-input produto-select'
            }),

            'quantidade': forms.NumberInput(attrs={
                'class': 'form-control gs-input quantidade-input',
                'step': '1',
                'min': '1'
            }),
        }

    def clean_quantidade(self):
        quantidade = self.cleaned_data.get('quantidade')
        if quantidade is None:
            return quantidade
        valor = Decimal(str(quantidade))
        if valor != valor.to_integral_value():
            raise forms.ValidationError(
                "Informe a quantidade em sacos inteiros."
            )
        if valor < 1:
            raise forms.ValidationError(
                "A quantidade deve ser pelo menos 1 saco."
            )
        return quantidade


class BaseItemVendaFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_messages = self.error_messages.copy()
        self.error_messages["too_few_forms"] = (
            "A venda deve possuir pelo menos um item."
        )


ItemVendaFormSet = inlineformset_factory(
    Venda,
    ItemVenda,
    form=ItemVendaForm,
    formset=BaseItemVendaFormSet,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ["cliente", "endereco", "cidade", "observacoes"]
        widgets = {
            "cliente": forms.Select(
                attrs={"class": "form-control gs-input js-cliente-pedido"}
            ),
            "endereco": forms.Textarea(
                attrs={
                    "class": "form-control gs-textarea",
                    "rows": 3,
                    "aria-describedby": "endereco-ajuda",
                    "placeholder": "Ex.: Rua das Flores, 123",
                }
            ),
            "cidade": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "observacoes": forms.Textarea(
                attrs={
                    "class": "form-control gs-input",
                    "rows": 3,
                    "placeholder": "Ponto de referência, horário ou quem recebe",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True).order_by(
            "nome"
        )
        self.fields["cliente"].empty_label = "Selecione o cliente"
        self.fields["observacoes"].required = False
        self.fields["cidade"].required = False
        self.fields["endereco"].error_messages["required"] = (
            "Informe o endereço do cliente antes de salvar o pedido."
        )

    def clean_endereco(self):
        endereco = (self.cleaned_data.get("endereco") or "").strip()
        if not endereco:
            raise forms.ValidationError(
                "Informe o endereço do cliente antes de salvar o pedido."
            )
        return endereco

    def clean_cidade(self):
        return (self.cleaned_data.get("cidade") or "").strip()


class ItemPedidoForm(forms.ModelForm):
    class Meta:
        model = ItemPedido
        fields = ["produto", "quantidade"]
        widgets = {
            "produto": forms.Select(
                attrs={"class": "form-control gs-input produto-select"}
            ),
            "quantidade": forms.NumberInput(
                attrs={
                    "class": "form-control gs-input quantidade-input",
                    "step": "1",
                    "min": "1",
                    "inputmode": "numeric",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["produto"].queryset = Produto.objects.filter(ativo=True).order_by(
            "peso_kg",
            "nome",
        )
        self.fields["produto"].empty_label = "Selecione o produto"
        self.fields["quantidade"].label = "Quantidade de sacos"
        if not self.is_bound:
            self.fields["quantidade"].initial = 1
        self.fields["quantidade"].error_messages["invalid"] = (
            "Informe a quantidade em sacos inteiros."
        )

    def clean_quantidade(self):
        quantidade = self.cleaned_data.get("quantidade")
        if quantidade is None:
            return quantidade
        if quantidade < 1:
            raise forms.ValidationError(
                "A quantidade deve ser pelo menos 1 saco."
            )
        return quantidade


class BaseItemPedidoFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_messages = self.error_messages.copy()
        self.error_messages["too_few_forms"] = (
            "Informe pelo menos %(num)d produto e a quantidade de sacos."
        )


ItemPedidoFormSet = inlineformset_factory(
    Pedido,
    ItemPedido,
    form=ItemPedidoForm,
    formset=BaseItemPedidoFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
