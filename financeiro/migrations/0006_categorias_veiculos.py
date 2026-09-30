from django.db import migrations


CATEGORIAS_NOVAS = [
    ("IPVA", "ipva", 65, True),
    ("Licenciamento", "licenciamento", 66, True),
]

SLUGS_EXIGE_VEICULO = {
    "ipva": True,
    "licenciamento": True,
    "combustivel": True,
    "veiculos": True,
    "seguros": True,
    "manutencao": False,
}


def atualizar_categorias(apps, schema_editor):
    CategoriaFinanceira = apps.get_model("financeiro", "CategoriaFinanceira")
    for nome, slug, ordem, exige_veiculo in CATEGORIAS_NOVAS:
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
    for slug, exige in SLUGS_EXIGE_VEICULO.items():
        CategoriaFinanceira.objects.filter(slug=slug).update(exige_veiculo=exige)


def reverter_categorias(apps, schema_editor):
    CategoriaFinanceira = apps.get_model("financeiro", "CategoriaFinanceira")
    CategoriaFinanceira.objects.filter(slug__in=["ipva", "licenciamento"]).delete()
    CategoriaFinanceira.objects.filter(slug="seguros").update(exige_veiculo=False)


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0005_obrigacaoveiculo_planomanutencao_veiculo_and_more"),
    ]

    operations = [
        migrations.RunPython(atualizar_categorias, reverter_categorias),
    ]
