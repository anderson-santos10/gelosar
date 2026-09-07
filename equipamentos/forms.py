from django import forms
from .models import Equipamento
from .models import DocumentoEquipamento


class EquipamentoForm(forms.ModelForm):
    class Meta:
        model = Equipamento

        fields = [
            'nome',
            'tipo',
            'cliente',
            'fabricante',
            'numero_serie',
            'valor_compra',
            'data_compra',
            'garantia_meses',
            'localizacao',
            'status',
            'observacoes',
        ]

        labels = {
            'nome': 'Nome do Equipamento',
            'tipo': 'Tipo',
            'cliente': 'Cliente',
            'fabricante': 'Fabricante',
            'numero_serie': 'Número de Série',
            'valor_compra': 'Valor de Compra',
            'data_compra': 'Data da Compra',
            'garantia_meses': 'Garantia (meses)',
            'localizacao': 'Localização',
            'status': 'Status',
            'observacoes': 'Observações',
        }

        widgets = {
            'data_compra': forms.DateInput(
                attrs={'type': 'date'}
            ),

            'observacoes': forms.Textarea(
                attrs={
                    'rows': 4,
                    'placeholder': 'Observações adicionais...'
                }
            ),
        }
        

class DocumentoEquipamentoForm(forms.ModelForm):
    class Meta:
        model = DocumentoEquipamento
        fields = ['nome', 'arquivo']
        
        
from django import forms

class ContratoComodatoForm(forms.Form):
    # BLOCO 1: DADOS DA EMPRESA / CLIENTE
    razao_social = forms.CharField(label="Razão Social / Nome Completo", max_length=255)
    nome_fantasia = forms.CharField(label="Nome Fantasia", max_length=255, required=False)
    cnpj_cpf = forms.CharField(label="CNPJ / CPF", max_length=20)
    inscricao_estadual = forms.CharField(label="Inscrição Estadual", max_length=30, required=False)
    
    # BLOCO 2: DADOS DO RESPONSÁVEL LEGAL & CONTATO
    responsavel_legal = forms.CharField(label="Nome do Responsável Legal", max_length=255)
    cpf_responsavel = forms.CharField(label="CPF do Responsável Legal", max_length=14)
    telefone = forms.CharField(label="Telefone / WhatsApp", max_length=20)
    email = forms.EmailField(label="E-mail de Contato")

    # BLOCO 3: ENDEREÇO DE INSTALAÇÃO
    cep = forms.CharField(label="CEP", max_length=10)
    endereco = forms.CharField(label="Logradouro (Rua/Av.)", max_length=255)
    numero = forms.CharField(label="Número", max_length=20)
    complemento = forms.CharField(label="Complemento", max_length=100, required=False)
    bairro = forms.CharField(label="Bairro", max_length=100)
    cidade_uf = forms.CharField(label="Cidade / UF", max_length=100)

    # BLOCO 4: DADOS DO EQUIPAMENTO
    descricao_equipamento = forms.CharField(
        label="Descrição do Equipamento", 
        max_length=255, 
        initial="CONSERVADOR DE GELO 1840 LITROS"
    )
    numero_serie = forms.CharField(label="Número de Série", max_length=100)
    especificacoes = forms.CharField(
        label="Especificações Técnicas / Voltagem", 
        max_length=255, 
        initial="220V 1F - STD (R-290)/BRANCA"
    )

    # BLOCO 5: FINALIZAÇÃO
    foro_comarca = forms.CharField(label="Comarca / Foro Eleito", max_length=100)
    data_assinatura = forms.DateField(
        label="Data da Assinatura", 
        widget=forms.DateInput(attrs={'type': 'date'})
    )