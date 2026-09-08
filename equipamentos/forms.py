from django import forms
from .models import ContratoComodato, DocumentoEquipamento
from .validators import validar_arquivo_documento


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
                attrs={"type": "date", "class": "form-control gs-input"}
            ),
            "data_fim": forms.DateInput(
                attrs={"type": "date", "class": "form-control gs-input"}
            ),
            "status": forms.Select(attrs={"class": "form-select gs-input"}),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-input", "rows": 3}
            ),
        }
