from django.db import models
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

    class Meta:
        ordering = ['-data_hora']

    def __str__(self):
        return (
            f'{self.equipamento.nome} - '
            f'{self.produto.nome} - '
            f'{self.quantidade}'
        )