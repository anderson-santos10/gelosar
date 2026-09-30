from django import forms
from django.core.exceptions import ValidationError

from .models import Cliente
from .utils import formatar_cnpj_cpf, normalizar_cnpj


class ClienteForm(forms.ModelForm):
    possui_equipamento_comodato = forms.TypedChoiceField(
        choices=((True, "Sim"), (False, "Não")),
        coerce=lambda valor: valor in (True, "True", "true", "1", 1),
        widget=forms.RadioSelect,
        label="Possui equipamento em comodato?",
        initial=False,
        required=True,
    )

    class Meta:
        model = Cliente
        fields = [
            "nome",
            "cnpj",
            "telefone",
            "email",
            "endereco",
            "cidade",
            "ativo",
            "possui_equipamento_comodato",
            "observacoes",
        ]
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Ex.: João da Silva",
                }
            ),
            "cnpj": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "maxlength": "18",
                    "placeholder": "Ex.: 00.000.000/0000-00",
                }
            ),
            "telefone": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Ex.: (14) 99999-9999",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Ex.: contato@empresa.com.br",
                }
            ),
            "cidade": forms.TextInput(
                attrs={
                    "class": "form-control gs-input",
                    "placeholder": "Ex.: Bauru",
                }
            ),
            "endereco": forms.Textarea(
                attrs={
                    "class": "form-control gs-textarea",
                    "rows": 3,
                    "placeholder": "Ex.: Rua das Flores, 123",
                }
            ),
            "observacoes": forms.Textarea(
                attrs={"class": "form-control gs-textarea", "rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vinculo_comodato_existente = False
        if self.instance.pk:
            self.vinculo_comodato_existente = (
                self.instance.equipamentos.exists()
                or self.instance.contratos_comodato.exists()
            )
            if self.instance.cnpj and "cnpj" not in self.data:
                self.initial["cnpj"] = formatar_cnpj_cpf(self.instance.cnpj)
            if self.vinculo_comodato_existente:
                self.initial["possui_equipamento_comodato"] = True

    def clean_cnpj(self):
        return normalizar_cnpj(self.cleaned_data.get("cnpj"))

    def clean_possui_equipamento_comodato(self):
        valor = self.cleaned_data["possui_equipamento_comodato"]
        if self.instance.pk and not valor:
            if (
                self.instance.equipamentos.exists()
                or self.instance.contratos_comodato.exists()
            ):
                raise ValidationError(
                    "Não é possível marcar Não enquanto houver equipamento "
                    "ou contrato de comodato vinculado a este cliente."
                )
        return valor
