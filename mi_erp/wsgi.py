import os
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.core.management import execute_from_command_line

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

def mantenimiento_total():
    try:
        with connection.cursor() as cursor:
            # 1. Crear tabla Perfil (la que usamos en las vistas)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_perfil (
                    id SERIAL PRIMARY KEY,
                    rol VARCHAR(20) NOT NULL,
                    tienda_id INTEGER REFERENCES inventario_tienda(id) ON DELETE CASCADE,
                    user_id INTEGER UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
                );
            """)
            # 2. Crear tabla Empleado (la que está pidiendo el Admin y da error)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_empleado (
                    id SERIAL PRIMARY KEY,
                    cargo VARCHAR(50) NOT NULL,
                    tienda_id INTEGER REFERENCES inventario_tienda(id) ON DELETE CASCADE,
                    user_id INTEGER UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
                );
            """)

            # --- NUEVA LÓGICA: ACTUALIZACIÓN DE TABLA CLIENTE ---
            # Agregamos las columnas necesarias para diferenciar Persona de Empresa
            cursor.execute("ALTER TABLE inventario_cliente ADD COLUMN IF NOT EXISTS dni VARCHAR(8);")
            cursor.execute("ALTER TABLE inventario_cliente ADD COLUMN IF NOT EXISTS ruc VARCHAR(11);")
            cursor.execute("ALTER TABLE inventario_cliente ADD COLUMN IF NOT EXISTS razon_social VARCHAR(200);")
            # ---------------------------------------------------

        print("Mantenimiento: Tablas sincronizadas correctamente.")
    except Exception as e:
        print(f"Error en mantenimiento: {e}")
        
    # 3. Recolectar estáticos para el diseño
    try:
        execute_from_command_line(['manage.py', 'collectstatic', '--noinput'])
    except:
        pass

mantenimiento_total()
app = application

