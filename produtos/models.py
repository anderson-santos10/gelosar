from django.db import models


class Produto(models.Model):

    nome = models.CharField(
        max_length=100,
        unique=True
    )

    peso_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    preco_venda = models.DecimalField(
        max_digits=10,
        decimal_places=2
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

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ["peso_kg"]

        constraints = [
            models.UniqueConstraint(
                fields=["peso_kg"],
                name="produto_peso_unico"
            )
        ]


class ComposicaoProduto(models.Model):

    produto = models.ForeignKey(
        Produto,
        on_delete=models.CASCADE,
        related_name="composicao"
    )

    insumo = models.ForeignKey(
        "insumos.Insumo",
        on_delete=models.PROTECT,
        related_name="composicoes"
    )

    quantidade = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=1
    )

    class Meta:
        verbose_name = "Composição do Produto"
        verbose_name_plural = "Composições dos Produtos"
        unique_together = ("produto", "insumo")

    def __str__(self):
        return (
            f"{self.produto.nome} → "
            f"{self.quantidade} {self.insumo.unidade} "
            f"de {self.insumo.nome}"
        )