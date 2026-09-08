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
