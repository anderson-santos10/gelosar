from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Venda(models.Model):

    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
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

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendas_criadas",
        editable=False,
    )


    class Meta:
        ordering = ['-data']


    def __str__(self):
        return f'Venda #{self.id} - {self.cliente.nome}'

    def _itens(self):
        """Reutiliza prefetch_related ou uma única consulta por instância."""
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "itens" in cache:
            return cache["itens"]
        itens = getattr(self, "_itens_lista", None)
        if itens is None:
            itens = list(self.itens.all())
            self._itens_lista = itens
        return itens

    @property
    def total(self):
        return sum(
            item.subtotal
            for item in self._itens()
        )
        
    @property
    def quantidade_total(self):
        return sum(
            item.quantidade
            for item in self._itens()
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


class Pedido(models.Model):
    """Solicitação do cliente antes de existir uma venda.

    A venda, a baixa de estoque e a conta a receber só nascem
    quando o pedido é marcado como entregue.
    """

    STATUS_ABERTO = "aberto"
    STATUS_ENTREGUE = "entregue"
    STATUS_CHOICES = [
        (STATUS_ABERTO, "Aberto"),
        (STATUS_ENTREGUE, "Entregue"),
    ]
    MENSAGEM_FECHADO = "Pedido entregue não pode ser alterado."

    cliente = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.PROTECT,
        related_name="pedidos",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ABERTO,
    )
    endereco = models.TextField(
        "Endereço de entrega",
        max_length=255,
        help_text="Cópia do endereço usado neste pedido. Não altera o cadastro do cliente.",
    )
    cidade = models.CharField(max_length=100, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos_criados",
        editable=False,
    )
    entregue_em = models.DateTimeField(null=True, blank=True, editable=False)
    entregue_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos_entregues",
        editable=False,
    )
    venda = models.OneToOneField(
        Venda,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pedido",
    )

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-criado_em", "-id"]
        permissions = [
            ("entregar_pedido", "Pode marcar pedido como entregue"),
        ]
        indexes = [
            models.Index(
                fields=["status", "criado_em"],
                name="vendas_ped_status_criado_idx",
            ),
        ]

    def __str__(self):
        return f"Pedido #{self.pk} — {self.cliente.nome}"

    def _status_persistido(self):
        if not self.pk:
            return None
        return (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
        )

    def clean(self):
        super().clean()
        erros = {}
        endereco = (self.endereco or "").strip()
        if not endereco:
            erros["endereco"] = (
                "Informe o endereço do cliente antes de salvar o pedido."
            )
        else:
            self.endereco = endereco
        self.cidade = (self.cidade or "").strip()

        if self.status == self.STATUS_ENTREGUE:
            if not self.entregue_em:
                erros["entregue_em"] = "Informe a data e a hora da entrega."
            if not self.entregue_por_id:
                erros["entregue_por"] = "Informe quem confirmou a entrega."
            if not self.venda_id:
                erros["venda"] = "Pedido entregue precisa estar ligado a uma venda."
        elif self.entregue_em or self.entregue_por_id or self.venda_id:
            erros["status"] = "Pedido aberto não pode ter entrega nem venda."

        if self.pk and self._status_persistido() == self.STATUS_ENTREGUE:
            erros["__all__"] = self.MENSAGEM_FECHADO

        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        if self._status_persistido() == self.STATUS_ENTREGUE:
            raise ValidationError({"__all__": [self.MENSAGEM_FECHADO]})
        super().save(*args, **kwargs)

    def _itens(self):
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "itens" in cache:
            return cache["itens"]
        return self.itens.all()

    @property
    def total(self):
        return sum((item.subtotal for item in self._itens()), Decimal("0.00"))


class ItemPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    produto = models.ForeignKey(
        "produtos.Produto",
        on_delete=models.PROTECT,
    )
    quantidade = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        error_messages={"invalid": "Informe a quantidade em sacos inteiros."},
    )
    preco_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )

    def save(self, *args, **kwargs):
        if self.preco_unitario is None and self.produto_id:
            self.preco_unitario = self.produto.preco_venda
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        if self.preco_unitario is None:
            return Decimal("0.00")
        return Decimal(self.quantidade) * self.preco_unitario

    def __str__(self):
        return f"{self.quantidade} × {self.produto.nome}"