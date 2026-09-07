from django.db import models
from insumos.models import Insumo

# Create your models here.
class CompraInsumo(models.Model):
    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.PROTECT
    )

    quantidade = models.PositiveIntegerField()

    valor_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=4
    )

    data_compra = models.DateField()

    fornecedor = models.CharField(
        max_length=150
    )