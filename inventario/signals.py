# inventario/signals.py
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import LoginLog, Compra, DetalleComprobante, MovimientoStock, Producto

# ==============================================================================
# LÓGICA EXISTENTE: REGISTRO DE LOGUEOS (RESPETADA 100%)
# ==============================================================================

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Registra un log cuando un usuario inicia sesión exitosamente."""
    LoginLog.objects.create(
        user=user,
        username_tried=user.username, # Nombre de usuario real que inició sesión
        ip_address=request.META.get('REMOTE_ADDR'),
        is_successful=True
    )

@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    """Registra un log cuando un intento de inicio de sesión falla."""
    username = credentials.get('username', 'N/A') # Obtiene el username intentado
    LoginLog.objects.create(
        user=None, # No hay usuario asociado si falló
        username_tried=username,
        ip_address=request.META.get('REMOTE_ADDR'),
        is_successful=False
    )

# ==============================================================================
# NUEVA LÓGICA: KARDEX (AUDITORÍA DE MOVIMIENTOS DE STOCK)
# ==============================================================================

@receiver(post_save, sender=Compra)
def registrar_kardex_compra(sender, instance, created, **kwargs):
    """
    Cada vez que se registra una COMPRA, se genera automáticamente un 
    movimiento de ENTRADA en el Kardex.
    """
    if created:
        prod = instance.producto
        # El stock actual ya tiene sumada la cantidad (por el save previo)
        # Calculamos el stock que había antes de la compra
        stock_anterior = prod.stock - instance.cantidad

        MovimientoStock.objects.create(
            producto=prod,
            tipo='ENTRADA',
            cantidad=instance.cantidad,
            stock_antes=stock_anterior,
            stock_despues=prod.stock,
            motivo=f"Compra: Ingreso de mercadería (Proveedor: {instance.proveedor.razon_social})"
        )

@receiver(post_save, sender=DetalleComprobante)
def registrar_kardex_venta(sender, instance, created, **kwargs):
    """
    Cada vez que se emite un comprobante, cada ítem vendido genera 
    un movimiento de SALIDA en el Kardex.
    """
    if created:
        prod = instance.producto
        # El stock ya fue restado en la lógica del POS
        # Calculamos el stock que había antes de la venta
        stock_anterior = prod.stock + instance.cantidad

        MovimientoStock.objects.create(
            producto=prod,
            tipo='SALIDA',
            cantidad=instance.cantidad,
            stock_antes=stock_anterior,
            stock_despues=prod.stock,
            motivo=f"Venta: {instance.comprobante.get_tipo_comprobante_display()} {instance.comprobante.serie}-{instance.comprobante.numero}"
        )
