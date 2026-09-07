from django.db import models
from insumos.models import Insumo
from produtos.models import Produto

# Create your models here.
class MovimentacaoInsumo(models.Model):

    TIPOS = [
        ("ENTRADA", "Entrada"),
        ("SAIDA", "Saída"),
        ("AJUSTE", "Ajuste"),
    ]

    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.PROTECT,
        related_name="movimentacoes"
    )

    tipo = models.CharField(
        max_length=10,
        choices=TIPOS
    )

    quantidade = models.PositiveIntegerField()

    observacao = models.TextField(
        blank=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.insumo.nome} - {self.tipo}"
    
    
class MovimentacaoProduto(models.Model):

    TIPOS = [
        ("ENTRADA", "Entrada"),
        ("SAIDA", "Saída"),
        ("AJUSTE", "Ajuste"),
    ]

    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name="movimentacoes"
    )

    tipo = models.CharField(
        max_length=10,
        choices=TIPOS
    )

    quantidade = models.PositiveIntegerField()

    observacao = models.TextField(
        blank=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.produto.nome} - {self.tipo}"