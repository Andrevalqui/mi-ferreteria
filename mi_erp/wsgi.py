import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

# --- TRUCO TEMPORAL PARA VERCEL ---
from django.core.management import execute_from_command_line
try:
    execute_from_command_line(['manage.py', 'migrate', '--noinput'])
except Exception as e:
    print(f"Error en migraciones: {e}")
# ----------------------------------

app = application
