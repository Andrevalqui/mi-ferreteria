# mi_erp/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "Administración | La Esquina del Shot"
admin.site.site_title = "La Esquina del Shot"
admin.site.index_title = "Administrador"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('inventario/', include('inventario.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
