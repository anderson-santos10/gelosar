from django.db import migrations, models


def nulos_em_serie_vazia(apps, schema_editor):
    Equipamento = apps.get_model("equipamentos", "Equipamento")
    Equipamento.objects.filter(numero_serie="").update(numero_serie=None)


class Migration(migrations.Migration):

    dependencies = [
        ("equipamentos", "0004_alter_documentoequipamento_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="equipamento",
            name="numero_serie",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.RunPython(nulos_em_serie_vazia, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="equipamento",
            name="numero_serie",
            field=models.CharField(
                blank=True, max_length=100, null=True, unique=True
            ),
        ),
    ]
