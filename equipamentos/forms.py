from django import forms

from clientes.models import Cliente

from .models import ContratoComodato, DocumentoEquipamento, Equipamento
from .validators import validar_arquivo_documento


def localizacao_do_cliente(cliente):
    """Copia o endereço já cadastrado no cliente para o limite do campo."""
    if cliente is None:
        return ""
    limite = Equipamento._meta.get_field("localizacao").max_length
    endereco = (cliente.endereco or "").strip()
    return endereco[:limite]


def enderecos_por_cliente():
    return {
        str(cliente.pk): localizacao_do_cliente(cliente)
        for cliente in Cliente.objects.only("id", "endereco")
    }


class EquipamentoForm(forms.ModelForm):
    class Meta:
        model = Equipamento
        fields = [
            "nome",
            "tipo",
            "cliente",
            "fabricante",
            "numero_serie",
            "valor_compra",
            "data_compra",
            "garantia_meses",
            "localizacao",
            "status",
            "observacoes",
        ]

    def clean(self):
        cleaned = super().clean()
        cliente = cleaned.get("cliente")
        if cliente is not None:
            cleaned["localizacao"] = localizacao_do_cliente(cliente)
        return cleaned


class DocumentoEquipamentoForm(forms.ModelForm):
    class Meta:
        model = DocumentoEquipamento
        fields = ['nome', 'arquivo']
        help_texts = {
            'arquivo': 'PDF, PNG, JPEG, DOCX ou XLSX.',
        }

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo:
            validar_arquivo_documento(arquivo)
        return arquivo


class ContratoComodatoForm(forms.ModelForm):
    class Meta:
        model = ContratoComodato
        fields = [
            "numero_contrato",
            "cliente",
            "equipamento",
            "data_inicio",
            "data_fim",
            "status",
            "observacoes",
        ]
        widgets = {
            "numero_contrato": forms.TextInput(attrs={"class": "form-control gs-input"}),
            "cliente": forms.Select(attrs={"class": "form-select gs-input"}),
            "equipamento": forms.Select(attrs={"class": "form-select gs-input"}),
            "data_inicio": forms.DateInput(
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"}
            ),
            "data_fim": forms.DateInput(
                attrs={"type": "date", "class": "form-control gs-input", "title": "Selecione a data"}
            ),
            "status": forms.Select(attrs={"class": "form-select gs-input"}),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-input", "rows": 3}
            ),
        }
