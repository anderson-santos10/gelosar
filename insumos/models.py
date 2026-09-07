from django.db import models

# Create your models here.
class Insumo(models.Model):
    nome = models.CharField(
        max_length=100,
        unique=True
    )

    unidade = models.CharField(
        max_length=20,
        default="un"
    )

    estoque_minimo = models.PositiveIntegerField(
        default=0
    )
    

    ativo = models.BooleanField(
        default=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    atualizado_em = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = "Insumo"
        verbose_name_plural = "Insumos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome