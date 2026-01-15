import os
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.core.management import execute_from_command_line

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

def mantenimiento_servidor():
    # 1. REPARAR BASE DE DATOS (Columnas y Tablas)
    try:
        with connection.cursor() as cursor:
            # Reparar columna unidad_medida
            cursor.execute("ALTER TABLE inventario_producto ADD COLUMN IF NOT EXISTS unidad_medida VARCHAR(20) DEFAULT 'UND';")
            
            # Crear tabla Perfil si no existe (Basado en tu modelo)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_perfil (
                    id SERIAL PRIMARY KEY,
                    rol VARCHAR(20) NOT NULL,
                    tienda_id INTEGER REFERENCES inventario_tienda(id),
                    user_id INTEGER UNIQUE REFERENCES auth_user(id)
                );
            """)
        print("Mantenimiento de tablas completado.")
    except Exception as e:
        print(f"Error DB: {e}")

    # 2. REPARAR DISEÑO (CSS)
    try:
        execute_from_command_line(['manage.py', 'collectstatic', '--noinput'])
    except Exception as e:
        print(f"Error Static: {e}")

mantenimiento_servidor()
app = application
