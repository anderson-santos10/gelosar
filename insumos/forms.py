from django import forms

from .models import Insumo


class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumo
        fields = [
            "nome",
            "unidade",
            "estoque_minimo",
            "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Saco plástico 5 kg"}),
            "unidade": forms.TextInput(attrs={"placeholder": "Ex.: unidade"}),
        }
