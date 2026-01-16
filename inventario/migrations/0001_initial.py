from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CajaDiaria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_apertura', models.DateTimeField(auto_now_add=True)),
                ('fecha_cierre', models.DateTimeField(blank=True, null=True)),
                ('monto_inicial', models.DecimalField(decimal_places=2, default=0.0, max_digits=10, verbose_name='Monto de Apertura')),
                ('monto_final_sistema', models.DecimalField(decimal_places=2, default=0.0, max_digits=10, verbose_name='Calculado por Sistema')),
                ('monto_final_real', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Dinero en Cajón')),
                ('diferencia', models.DecimalField(decimal_places=2, default=0.0, help_text='Positivo sobra, Negativo falta', max_digits=10)),
                ('estado', models.CharField(choices=[('ABIERTA', 'Abierta'), ('CERRADA', 'Cerrada')], default='ABIERTA', max_length=10)),
                ('observaciones', models.TextField(blank=True, null=True)),
                # Aquí asumimos que la tabla inventario_tienda YA EXISTE en tu base de datos
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cajas', to='inventario.tienda')),
                ('usuario_apertura', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cajas_abiertas', to=settings.AUTH_USER_MODEL)),
                ('usuario_cierre', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cajas_cerradas', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='MovimientoCaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('INGRESO', 'Ingreso Dinero'), ('EGRESO', 'Salida/Gasto')], max_length=10)),
                ('monto', models.DecimalField(decimal_places=2, max_digits=10)),
                ('concepto', models.CharField(help_text='Ej: Pago de almuerzo, taxi, compra escoba', max_length=200)),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('caja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='movimientos', to='inventario.cajadiaria')),
                ('usuario', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
