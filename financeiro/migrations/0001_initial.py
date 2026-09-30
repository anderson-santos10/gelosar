from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CategoriaFinanceira",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nome", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("despesa", "Despesa"),
                            ("investimento", "Investimento"),
                            ("receita", "Receita"),
                        ],
                        default="despesa",
                        max_length=20,
                    ),
                ),
                ("ativo", models.BooleanField(default=True)),
                ("ordem", models.PositiveIntegerField(default=0)),
                (
                    "exige_veiculo",
                    models.BooleanField(
                        default=False,
                        help_text="Reservado para contas futuras que devam exigir veículo.",
                    ),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Categoria financeira",
                "verbose_name_plural": "Categorias financeiras",
                "ordering": ["ordem", "nome"],
            },
        ),
        migrations.CreateModel(
            name="Fornecedor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nome", models.CharField(max_length=150)),
                ("cnpj", models.CharField(blank=True, max_length=18, null=True)),
                ("telefone", models.CharField(blank=True, max_length=20)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("observacoes", models.TextField(blank=True)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Fornecedor",
                "verbose_name_plural": "Fornecedores",
                "ordering": ["nome"],
            },
        ),
        migrations.AddConstraint(
            model_name="fornecedor",
            constraint=models.UniqueConstraint(
                condition=models.Q(cnpj__isnull=False),
                fields=("cnpj",),
                name="financeiro_fornecedor_cnpj_unico",
            ),
        ),
    ]
