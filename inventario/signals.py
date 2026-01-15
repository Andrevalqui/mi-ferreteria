# inventario/signals.py
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from .models import LoginLog

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
