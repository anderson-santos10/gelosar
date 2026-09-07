from django import forms
from .models import Producao


class ProducaoForm(forms.ModelForm):
    class Meta:
        model = Producao
        fields = [
            "equipamento",
            "produto",
            "quantidade",
            "observacao",
        ]
        widgets = {
            "equipamento": forms.Select(attrs={"class": "form-control gs-input"}),
            "produto": forms.Select(attrs={"class": "form-control gs-input"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control gs-input"}),
            "observacao": forms.Textarea(attrs={"class": "form-control gs-input", "rows": 3}),
        }