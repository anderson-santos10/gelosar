from django.db import models


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

    observacoes = models.TextField(
        blank=True
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    atualizado_em = models.DateTimeField(
        auto_now=True
    )


    def __str__(self):
        return self.nome