from django import forms

from .models import MovimentacaoInsumo, MovimentacaoProduto
from .services import QuantidadeNaoInteira, quantidade_para_movimento


class EntradaInsumoForm(forms.ModelForm):

    class Meta:
        model = MovimentacaoInsumo

        fields = [
            "insumo",
            "quantidade",
            "observacao",
        ]

        widgets = {

            "insumo": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "quantidade": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "placeholder": "Digite a quantidade",
                }
            ),

            "observacao": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Ex.: Compra de embalagens",
                }
            ),
        }

    def save(self, commit=True):

        movimentacao = super().save(commit=False)

        movimentacao.tipo = "ENTRADA"

        if commit:
            movimentacao.save()

        return movimentacao


class AjusteProdutoForm(forms.ModelForm):
    """AJUSTE positivo apenas (PositiveIntegerField). Não aceita negativo."""

    class Meta:
        model = MovimentacaoProduto
        fields = [
            "produto",
            "quantidade",
            "observacao",
        ]
        widgets = {
            "produto": forms.Select(attrs={"class": "form-select"}),
            "quantidade": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "placeholder": "Quantidade a acrescer",
                }
            ),
            "observacao": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
        }

    def clean_quantidade(self):
        quantidade = self.cleaned_data.get("quantidade")
        try:
            quantidade_para_movimento(quantidade)
        except QuantidadeNaoInteira as exc:
            raise forms.ValidationError(str(exc)) from exc
        return quantidade

    def save(self, commit=True):
        movimentacao = super().save(commit=False)
        movimentacao.tipo = "AJUSTE"
        if commit:
            movimentacao.save()
        return movimentacao