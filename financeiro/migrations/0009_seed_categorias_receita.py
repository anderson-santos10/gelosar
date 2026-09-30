from django.db import migrations


CATEGORIAS = [
    ("Vendas", "vendas-receita", 10),
    ("Serviços", "servicos", 20),
    ("Ressarcimento", "ressarcimento", 30),
    ("Outras receitas", "outras-receitas", 40),
]


def criar_categorias(apps, schema_editor):
    CategoriaFinanceira = apps.get_model("financeiro", "CategoriaFinanceira")
    for nome, slug, ordem in CATEGORIAS:
        CategoriaFinanceira.objects.get_or_create(
            slug=slug,
            defaults={
                "nome": nome,
                "tipo": "receita",
                "ativo": True,
                "ordem": ordem,
                "exige_veiculo": False,
            },
        )


def remover_categorias(apps, schema_editor):
    CategoriaFinanceira = apps.get_model("financeiro", "CategoriaFinanceira")
    slugs = [item[1] for item in CATEGORIAS]
    CategoriaFinanceira.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0008_contareceber"),
    ]

    operations = [
        migrations.RunPython(criar_categorias, remover_categorias),
    ]
