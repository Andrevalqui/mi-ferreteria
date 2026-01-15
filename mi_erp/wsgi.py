import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

# --- TRUCO ACTUALIZADO PARA CREAR COLUMNAS FALTANTES ---
from django.core.management import execute_from_command_line
try:
    # 1. Esto detecta que falta 'unidad_medida' y crea el archivo de migración
    execute_from_command_line(['manage.py', 'makemigrations', 'inventario', '--noinput'])
    # 2. Esto aplica el cambio a la base de datos de Neon
    execute_from_command_line(['manage.py', 'migrate', 'inventario', '--noinput'])
except Exception as e:
    print(f"Error en migraciones: {e}")
# -----------------------------------------------------

app = application
