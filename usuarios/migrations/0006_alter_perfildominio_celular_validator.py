import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0005_usuario_email_verificado_usuario_estado_solicitud"),
    ]

    operations = [
        migrations.AlterField(
            model_name="perfildominio",
            name="celular",
            field=models.CharField(
                blank=True,
                max_length=12,
                validators=[
                    django.core.validators.RegexValidator(
                        regex="^\\+591[0-9]{8}$"
                    )
                ],
            ),
        ),
    ]
