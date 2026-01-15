import os
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.core.management import execute_from_command_line # IMPORTANTE: Agregamos esta línea

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

# --- MANTENIMIENTO INTEGRAL (DB + DISEÑO) ---
def mantenimiento_servidor():
    # 1. REPARAR BASE DE DATOS (Campo unidad_medida)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE inventario_producto 
                ADD COLUMN IF NOT EXISTS unidad_medida VARCHAR(20) DEFAULT 'UND';
            """)
        print("Base de datos verificada.")
    except Exception as e:
        print(f"Log DB: {e}")

    # 2. REPARAR DISEÑO (CSS del Admin)
    try:
        # Esto extrae los CSS de Django y los pone donde WhiteNoise pueda verlos
        execute_from_command_line(['manage.py', 'collectstatic', '--noinput'])
        print("Archivos estáticos recolectados.")
    except Exception as e:
        print(f"Log Static: {e}")

# Ejecutamos las dos reparaciones
mantenimiento_servidor()
# --------------------------------------------

app = application
