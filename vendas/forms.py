from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal

from .models import Venda, ItemVenda


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
                'placeholder': 'Observações do pedido...'
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


ItemVendaFormSet = inlineformset_factory(
    Venda,
    ItemVenda,
    form=ItemVendaForm,
    extra=1,
    can_delete=True
)