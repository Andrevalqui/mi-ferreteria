from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver

# === MODELO MULTI-TENANT (Tienda) ===
class Tienda(models.Model):
    propietario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tienda')
    nombre = models.CharField(max_length=100)
    ruc = models.CharField(max_length=11, default='00000000000')
    direccion = models.CharField(max_length=255, blank=True, null=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    logo = models.ImageField(upload_to='logos_tiendas/', blank=True, null=True, 
                             help_text="Logo de la tienda (se mostrará en la interfaz)")

    def __str__(self):
        return self.nombre

# --- Modelos de Datos Asociados a Tienda ---

class Producto(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos')
    nombre = models.CharField(max_length=100)
    codigo_barras = models.CharField(max_length=100, blank=True, null=True)
    # CAMBIO FERRETERÍA: DecimalField para permitir 1.5 metros, etc.
    stock = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    costo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # NUEVO CAMPO: Para saber si se vende por Metro, Kilo, Unidad
    unidad_medida = models.CharField(max_length=20, default='UND', help_text="Ej: UND, MTS, KG, LTS, CAJA")

    class Meta:
        unique_together = ('tienda', 'codigo_barras')
        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    def __str__(self):
        return f"{self.nombre} ({self.tienda.nombre})"


class Proveedor(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='proveedores')
    razon_social = models.CharField(max_length=200, verbose_name="Razón Social")
    ruc = models.CharField(max_length=11, verbose_name="RUC")
    direccion = models.CharField(max_length=255, blank=True, verbose_name="Dirección")
    telefono = models.CharField(max_length=20, blank=True, verbose_name="Teléfono")
    email = models.EmailField(blank=True, verbose_name="Email")
    pagina_web = models.URLField(max_length=200, blank=True, verbose_name="Página Web")

    class Meta:
        unique_together = ('tienda', 'ruc')
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"

    def __str__(self):
        return f"{self.razon_social} ({self.tienda.nombre})"


class Cliente(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='clientes')
    
    # --- División Persona / Empresa ---
    nombre_completo = models.CharField(max_length=200, verbose_name="Nombre Completo", blank=True, null=True)
    dni = models.CharField(max_length=8, blank=True, null=True, verbose_name="DNI")
    
    razon_social = models.CharField(max_length=200, verbose_name="Razón Social", blank=True, null=True)
    ruc = models.CharField(max_length=11, blank=True, null=True, verbose_name="RUC")
    # ----------------------------------

    # Mantenemos dni_ruc para no romper la lógica de unique_together actual
    dni_ruc = models.CharField(max_length=11, blank=True, null=True, verbose_name="DNI o RUC (Legacy)")
    telefono = models.CharField(max_length=20, blank=True, verbose_name="Teléfono")
    email = models.EmailField(blank=True)
    pagina_web = models.URLField(max_length=200, blank=True, verbose_name="Página Web")

    class Meta:
        unique_together = ('tienda', 'dni_ruc')
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        # Lógica para mostrar Razón Social si existe, sino Nombre Completo
        nombre_a_mostrar = self.razon_social if self.razon_social else self.nombre_completo
        return f"{nombre_a_mostrar} ({self.tienda.nombre})"

class Venta(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas')
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_realizadas')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='ventas_producto')
    # CAMBIO FERRETERÍA: DecimalField
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_de_venta = models.DateTimeField(auto_now_add=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_de_venta']

    def __str__(self):
        return f'Venta de {self.cantidad} x {self.producto.nombre} el {self.fecha_de_venta.strftime("%d/%m/%Y %H:%M")} ({self.tienda.nombre})'


class Compra(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='compras')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, related_name='compras_realizadas')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='compras_producto')
    # CAMBIO FERRETERÍA: DecimalField
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    costo_total = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_de_compra = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Compra"
        verbose_name_plural = "Compras"
        ordering = ['-fecha_de_compra']

    def __str__(self):
        proveedor_nombre = self.proveedor.razon_social if self.proveedor else "Proveedor Eliminado"
        return f'Compra de {self.cantidad} x {self.producto.nombre} a {proveedor_nombre} ({self.tienda.nombre})'

class Comprobante(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='comprobantes')
    TIPO_COMPROBANTE_CHOICES = [
        ('BOLETA', 'Boleta de Venta'),
        ('FACTURA', 'Factura'),
    ]
    ESTADO_COMPROBANTE_CHOICES = [
        ('EMITIDO', 'Emitido'),
        ('ANULADO', 'Anulado'),
        ('PENDIENTE', 'Pendiente de Pago'),
        ('PAGADO', 'Pagado'),
    ]

    tipo_comprobante = models.CharField(max_length=10, choices=TIPO_COMPROBANTE_CHOICES, default='BOLETA')
    serie = models.CharField(max_length=4, help_text="Serie del comprobante (ej. B001, F001)")
    numero = models.IntegerField(help_text="Número correlativo del comprobante")
    fecha_emision = models.DateTimeField(auto_now_add=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True,
                                 help_text="Cliente asociado al comprobante", related_name='comprobantes_emitidos')

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    igv = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_final = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    estado = models.CharField(max_length=10, choices=ESTADO_COMPROBANTE_CHOICES, default='EMITIDO')
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('tienda', 'tipo_comprobante', 'serie', 'numero')
        verbose_name = "Comprobante"
        verbose_name_plural = "Comprobantes"
        ordering = ['-fecha_emision']

    def __str__(self):
        return f"{self.tienda.nombre} - {self.tipo_comprobante} {self.serie}-{self.numero} - Total: {self.total_final}"

    def save(self, *args, **kwargs):
        if not self.pk:
            last_comprobante = Comprobante.objects.filter(
                tienda=self.tienda,
                tipo_comprobante=self.tipo_comprobante,
                serie=self.serie
            ).order_by('-numero').first()

            if last_comprobante:
                self.numero = last_comprobante.numero + 1
            else:
                self.numero = 1
        super().save(*args, **kwargs)

class DetalleComprobante(models.Model):
    comprobante = models.ForeignKey(Comprobante, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    # CAMBIO FERRETERÍA: DecimalField para cantidad
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, help_text="Precio unitario SIN IGV")
    precio_unitario_con_igv = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Precio unitario CON IGV (el precio de venta final)",
        null=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cantidad * Precio Unitario (SIN IGV)")
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Detalle de Comprobante"
        verbose_name_plural = "Detalles de Comprobante"

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre} en {self.comprobante.tipo_comprobante}-{self.comprobante.numero}"

    def save(self, *args, **kwargs):
        # Convertir a Decimal si es float para evitar errores
        self.subtotal = Decimal(str(self.cantidad)) * Decimal(str(self.precio_unitario))
        super().save(*args, **kwargs)


@receiver(post_save, sender=Compra)
def actualizar_stock_post_compra(sender, instance, created, **kwargs):
    if created:
        producto = instance.producto
        if producto.tienda == instance.tienda:
            producto.stock += instance.cantidad
            producto.save()
            print(f"SEÑAL RECIBIDA: Stock de '{producto.nombre}' actualizado.")
        else:
            print(f"ERROR: Tiendas no coinciden.")

class LoginLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='login_logs')
    username_tried = models.CharField(max_length=150, help_text="Nombre de usuario que se intentó usar")
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_successful = models.BooleanField(default=False)

    def __str__(self):
        status = "Éxito" if self.is_successful else "Fallo"
        user_info = self.user.username if self.user else self.username_tried
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {user_info} - {status}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Registro de Logueo"
        verbose_name_plural = "Registros de Logueos"
        
class Perfil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='miembros')
    rol = models.CharField(max_length=20, choices=[('VENDEDOR', 'Vendedor'), ('ADMIN', 'Administrador Local')], default='VENDEDOR')

    def __str__(self):
        return f"{self.user.username} - {self.tienda.nombre} ({self.rol})"

class CajaDiaria(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='cajas')
    usuario_apertura = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cajas_abiertas')
    usuario_cierre = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cajas_cerradas')
    
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    
    monto_inicial = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Monto de Apertura")
    monto_final_sistema = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Calculado por Sistema")
    monto_final_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Dinero en Cajón")
    diferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Positivo sobra, Negativo falta")
    
    estado = models.CharField(max_length=10, choices=[('ABIERTA', 'Abierta'), ('CERRADA', 'Cerrada')], default='ABIERTA')
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Caja {self.id} - {self.fecha_apertura.strftime('%d/%m/%Y')} ({self.estado})"

class MovimientoCaja(models.Model):
    TIPOS = [('INGRESO', 'Ingreso Dinero'), ('EGRESO', 'Salida/Gasto')]
    
    caja = models.ForeignKey(CajaDiaria, on_delete=models.CASCADE, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    concepto = models.CharField(max_length=200, help_text="Ej: Pago de almuerzo, taxi, compra escoba")
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.tipo}: {self.monto} - {self.concepto}"
