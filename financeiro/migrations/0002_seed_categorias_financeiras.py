from django.db import migrations

CATEGORIAS = [
    ("Impostos", "impostos", 10, False),
    ("Aluguel", "aluguel", 20, False),
    ("Água", "agua", 30, False),
    ("Energia elétrica", "energia-eletrica", 40, False),
    ("Internet/Telefonia", "internet-telefonia", 50, False),
    ("Combustível", "combustivel", 60, True),
    ("Manutenção", "manutencao", 70, False),
    ("Veículos", "veiculos", 80, True),
    ("Equipamentos", "equipamentos", 90, False),
    ("Insumos", "insumos", 100, False),
    ("Embalagens", "embalagens", 110, False),
    ("Funcionários", "funcionarios", 120, False),
    ("Contabilidade", "contabilidade", 130, False),
    ("Seguros", "seguros", 140, False),
    ("Taxas bancárias", "taxas-bancarias", 150, False),
    ("Outros", "outros", 160, False),
]


def criar_categorias(apps, schema_editor):
    CategoriaFinanceira = apps.get_model("financeiro", "CategoriaFinanceira")
    for nome, slug, ordem, exige_veiculo in CATEGORIAS:
        CategoriaFinanceira.objects.get_or_create(
            slug=slug,
            defaults={
                "nome": nome,
                "tipo": "despesa",
                "ativo": True,
                "ordem": ordem,
                "exige_veiculo": exige_veiculo,
            },
        )


def remover_categorias(apps, schema_editor):
    CategoriaFinanceira = apps.get_model("financeiro", "CategoriaFinanceira")
    slugs = [item[1] for item in CATEGORIAS]
    CategoriaFinanceira.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_categorias, remover_categorias),
    ]
