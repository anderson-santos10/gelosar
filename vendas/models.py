from django.db import models


class Venda(models.Model):

    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.CASCADE,
        related_name='vendas'
    )

    data = models.DateField(
        auto_now_add=True
    )

    observacoes = models.TextField(
        blank=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )


    class Meta:
        ordering = ['-data']


    def __str__(self):
        return f'Venda #{self.id} - {self.cliente.nome}'


    @property
    def total(self):
        return sum(
            item.subtotal
            for item in self.itens.all()
        )
        
    @property
    def quantidade_total(self):
        return sum(
            item.quantidade
            for item in self.itens.all()
        )


class ItemVenda(models.Model):

    venda = models.ForeignKey(
        Venda,
        on_delete=models.CASCADE,
        related_name='itens'
    )

    produto = models.ForeignKey(
        'produtos.Produto',
        on_delete=models.PROTECT
    )

    quantidade = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    preco_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        editable=False
    )


    def save(self, *args, **kwargs):

        self.preco_unitario = self.produto.preco_venda

        super().save(*args, **kwargs)


    @property
    def subtotal(self):
        return self.quantidade * self.preco_unitario


    def __str__(self):
        return f'{self.produto.nome} - {self.quantidade}'