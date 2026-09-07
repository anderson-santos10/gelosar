from django import forms

from .models import MovimentacaoInsumo


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