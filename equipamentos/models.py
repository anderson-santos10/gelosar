from django.db import models


class Equipamento(models.Model):
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('manutencao', 'Manutenção'),
        ('parado', 'Parado'),
    ]

    TIPO_CHOICES = [
        ('maquina_gelo', 'Máquina de Gelo'),
        ('freezer', 'Freezer'),
        ('bomba', 'Bomba'),
        ('compressor', 'Compressor'),
        ('outro', 'Outro'),
    ]

    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipamentos'
    )

    nome = models.CharField(max_length=150)

    tipo = models.CharField(
        max_length=50,
        choices=TIPO_CHOICES,
        default='outro'
    )

    fabricante = models.CharField(
        max_length=100,
        blank=True
    )

    numero_serie = models.CharField(
        max_length=100,
        blank=True,
    )

    valor_compra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    data_compra = models.DateField(
        null=True,
        blank=True
    )

    garantia_meses = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    localizacao = models.CharField(
        max_length=150,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ativo'
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
        return f'{self.codigo} - {self.nome}'

    @property
    def codigo(self):
        return f'EQ{self.id:04d}' if self.id else 'Novo'

    class Meta:
        verbose_name = 'Equipamento'
        verbose_name_plural = 'Equipamentos'
        ordering = ['-id']


class DocumentoEquipamento(models.Model):
    equipamento = models.ForeignKey(
        Equipamento,
        on_delete=models.CASCADE,
        related_name='documentos'
    )

    nome = models.CharField(
        max_length=100
    )

    arquivo = models.FileField(
        upload_to='documentos_equipamentos/'
    )

    data_upload = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Documento do Equipamento'
        verbose_name_plural = 'Documentos dos Equipamentos'
        ordering = ['-data_upload']