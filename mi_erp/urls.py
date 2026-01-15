from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Configuración del Admin (Título)
admin.site.site_header = "Administración | Ferretería Master"
admin.site.site_title = "Ferretería Master"
admin.site.index_title = "Panel de Control"

urlpatterns = [
    path('admin/', admin.site.urls),
    # CAMBIO IMPORTANTE: Quitamos 'inventario/' y dejamos comillas vacías ''
    # Esto hace que la ferretería cargue en la página principal.
    path('', include('inventario.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
