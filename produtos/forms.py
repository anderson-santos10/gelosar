from django import forms

from .models import Produto


class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = [
            "nome",
            "peso_kg",
            "preco_venda",
            "estoque_minimo",
            "ativo",
        ]
