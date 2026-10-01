from django.db import models

from .utils import (
    apresentar_cidade,
    formatar_cnpj_cpf,
    formatar_telefone,
    normalizar_cnpj,
)


class Cliente(models.Model):

    nome = models.CharField(
        max_length=150
    )

    cnpj = models.CharField(
        max_length=18,
        unique=True,
        blank=True,
        null=True
    )

    telefone = models.CharField(
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    endereco = models.TextField(
        max_length=255,
        blank=True
    )

    cidade = models.CharField(
        max_length=100,
        blank=True
    )

    ativo = models.BooleanField(
        default=True
    )

    possui_equipamento_comodato = models.BooleanField(
        default=False,
        verbose_name="Possui equipamento em comodato",
        help_text=(
            "Declaração operacional: o cliente opera com equipamento em comodato, "
            "mesmo antes de um equipamento ou contrato específico estar vinculado."
        ),
    )

    observacoes = models.TextField(
        blank=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    atualizado_em = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.cnpj = normalizar_cnpj(self.cnpj)
        super().save(*args, **kwargs)

    @property
    def cnpj_formatado(self):
        return formatar_cnpj_cpf(self.cnpj)

    @property
    def telefone_formatado(self):
        return formatar_telefone(self.telefone)

    @property
    def cidade_apresentacao(self):
        return apresentar_cidade(self.cidade)

    @property
    def possui_comodato_efetivo(self):
        """
        Indicador de listagem/detalhe.

        Sim se a declaração estiver marcada ou se já existir equipamento
        ou contrato de comodato vinculado ao cliente.
        """
        anotado = getattr(self, "possui_comodato_lista", None)
        if anotado is not None:
            return bool(anotado)
        return (
            self.possui_equipamento_comodato
            or self.equipamentos.exists()
            or self.contratos_comodato.exists()
        )
