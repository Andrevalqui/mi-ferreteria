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
            name='Tienda',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('ruc', models.CharField(default='00000000000', max_length=11)),
                ('direccion', models.CharField(blank=True, max_length=255, null=True)),
                ('creada_en', models.DateTimeField(auto_now_add=True)),
                ('logo', models.ImageField(blank=True, help_text='Logo de la tienda', null=True, upload_to='logos_tiendas/')),
                ('propietario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='tienda', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Tienda',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('ruc', models.CharField(default='00000000000', max_length=11)),
                ('direccion', models.CharField(blank=True, max_length=255, null=True)),
                ('creada_en', models.DateTimeField(auto_now_add=True)),
                ('logo', models.ImageField(blank=True, help_text='Logo de la tienda', null=True, upload_to='logos_tiendas/')),
                ('propietario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='tienda', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Perfil',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rol', models.CharField(choices=[('VENDEDOR', 'Vendedor'), ('ADMIN', 'Administrador Local')], default='VENDEDOR', max_length=20)),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='miembros', to='inventario.tienda')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='perfil', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Producto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('codigo_barras', models.CharField(blank=True, max_length=100, null=True)),
                ('stock', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('costo', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('precio', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('unidad_medida', models.CharField(default='UND', help_text='Ej: UND, MTS, KG, LTS, CAJA', max_length=20)),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='productos', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Producto',
                'verbose_name_plural': 'Productos',
                'unique_together': {('tienda', 'codigo_barras')},
            },
        ),
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre_completo', models.CharField(blank=True, max_length=200, null=True, verbose_name='Nombre Completo')),
                ('dni', models.CharField(blank=True, max_length=8, null=True, verbose_name='DNI')),
                ('razon_social', models.CharField(blank=True, max_length=200, null=True, verbose_name='Razón Social')),
                ('ruc', models.CharField(blank=True, max_length=11, null=True, verbose_name='RUC')),
                ('dni_ruc', models.CharField(blank=True, max_length=11, null=True, verbose_name='DNI o RUC (Legacy)')),
                ('telefono', models.CharField(blank=True, max_length=20, verbose_name='Teléfono')),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('pagina_web', models.URLField(blank=True, verbose_name='Página Web')),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clientes', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
                'unique_together': {('tienda', 'dni_ruc')},
            },
        ),
        migrations.CreateModel(
            name='Proveedor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('razon_social', models.CharField(max_length=200, verbose_name='Razón Social')),
                ('ruc', models.CharField(max_length=11, verbose_name='RUC')),
                ('direccion', models.CharField(blank=True, max_length=255, verbose_name='Dirección')),
                ('telefono', models.CharField(blank=True, max_length=20, verbose_name='Teléfono')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Email')),
                ('pagina_web', models.URLField(blank=True, verbose_name='Página Web')),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proveedores', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Proveedor',
                'verbose_name_plural': 'Proveedores',
                'unique_together': {('tienda', 'ruc')},
            },
        ),
        migrations.CreateModel(
            name='Compra',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cantidad', models.DecimalField(decimal_places=2, max_digits=10)),
                ('costo_total', models.DecimalField(decimal_places=2, max_digits=10)),
                ('fecha_de_compra', models.DateTimeField(auto_now_add=True)),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compras_producto', to='inventario.producto')),
                ('proveedor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compras_realizadas', to='inventario.proveedor')),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compras', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Compra',
                'verbose_name_plural': 'Compras',
                'ordering': ['-fecha_de_compra'],
            },
        ),
        migrations.CreateModel(
            name='Venta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cantidad', models.DecimalField(decimal_places=2, max_digits=10)),
                ('precio_unitario', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('costo_unitario', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('total', models.DecimalField(decimal_places=2, max_digits=10)),
                ('fecha_de_venta', models.DateTimeField(auto_now_add=True)),
                ('observaciones', models.CharField(blank=True, max_length=255, null=True)),
                ('cliente', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ventas_realizadas', to='inventario.cliente')),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ventas_producto', to='inventario.producto')),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ventas', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Venta',
                'verbose_name_plural': 'Ventas',
                'ordering': ['-fecha_de_venta'],
            },
        ),
        migrations.CreateModel(
            name='Comprobante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_comprobante', models.CharField(choices=[('BOLETA', 'Boleta de Venta'), ('FACTURA', 'Factura')], default='BOLETA', max_length=10)),
                ('serie', models.CharField(help_text='Serie del comprobante (ej. B001, F001)', max_length=4)),
                ('numero', models.IntegerField(help_text='Número correlativo del comprobante')),
                ('fecha_emision', models.DateTimeField(auto_now_add=True)),
                ('subtotal', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('igv', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('total_final', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('estado', models.CharField(choices=[('EMITIDO', 'Emitido'), ('ANULADO', 'Anulado'), ('PENDIENTE', 'Pendiente de Pago'), ('PAGADO', 'Pagado')], default='EMITIDO', max_length=10)),
                ('observaciones', models.TextField(blank=True, null=True)),
                ('cliente', models.ForeignKey(blank=True, help_text='Cliente asociado al comprobante', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='comprobantes_emitidos', to='inventario.cliente')),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comprobantes', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Comprobante',
                'verbose_name_plural': 'Comprobantes',
                'ordering': ['-fecha_emision'],
                'unique_together': {('tienda', 'tipo_comprobante', 'serie', 'numero')},
            },
        ),
        migrations.CreateModel(
            name='DetalleComprobante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cantidad', models.DecimalField(decimal_places=2, max_digits=10)),
                ('precio_unitario', models.DecimalField(decimal_places=2, help_text='Precio unitario SIN IGV', max_digits=10)),
                ('precio_unitario_con_igv', models.DecimalField(decimal_places=2, help_text='Precio unitario CON IGV', max_digits=10, null=True)),
                ('subtotal', models.DecimalField(decimal_places=2, help_text='Cantidad * Precio Unitario (SIN IGV)', max_digits=10)),
                ('costo_unitario', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('comprobante', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='detalles', to='inventario.comprobante')),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inventario.producto')),
            ],
            options={
                'verbose_name': 'Detalle de Comprobante',
                'verbose_name_plural': 'Detalles de Comprobante',
            },
        ),
        migrations.CreateModel(
            name='LoginLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username_tried', models.CharField(help_text='Nombre de usuario que se intentó usar', max_length=150)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('is_successful', models.BooleanField(default=False)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='login_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Registro de Logueo',
                'verbose_name_plural': 'Registros de Logueos',
                'ordering': ['-timestamp'],
            },
        ),
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
