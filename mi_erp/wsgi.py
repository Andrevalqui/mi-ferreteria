import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

# AGREGA ESTA LÍNEA AL FINAL (Es el "traductor" para Vercel)
app = application
