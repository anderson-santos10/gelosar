from django.conf import settings
from django.db import models
from equipamentos.models import Equipamento
from produtos.models import Produto


class Producao(models.Model):

    equipamento = models.ForeignKey(
        Equipamento,
        on_delete=models.PROTECT,
        limit_choices_to={
            'tipo': 'maquina_gelo'
        }
    )

    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT
    )

    quantidade = models.PositiveIntegerField()

    data_hora = models.DateTimeField(
        auto_now_add=True
    )

    observacao = models.TextField(
        blank=True
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="producoes_criadas",
        editable=False,
    )

    class Meta:
        ordering = ['-data_hora']

    def __str__(self):
        return (
            f'{self.equipamento.nome} - '
            f'{self.produto.nome} - '
            f'{self.quantidade}'
        )