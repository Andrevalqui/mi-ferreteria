import os
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.core.management import execute_from_command_line

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

def mantenimiento_total():
    try:
        with connection.cursor() as cursor:
            # 1. Crear tabla Perfil (Original)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_perfil (
                    id SERIAL PRIMARY KEY,
                    rol VARCHAR(20) NOT NULL,
                    tienda_id INTEGER REFERENCES inventario_tienda(id) ON DELETE CASCADE,
                    user_id INTEGER UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
                );
            """)
            # 2. Crear tabla Empleado (Original)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_empleado (
                    id SERIAL PRIMARY KEY,
                    cargo VARCHAR(50) NOT NULL,
                    tienda_id INTEGER REFERENCES inventario_tienda(id) ON DELETE CASCADE,
                    user_id INTEGER UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
                );
            """)

            # 3. Actualización de Cliente (Original)
            cursor.execute("ALTER TABLE inventario_cliente ADD COLUMN IF NOT EXISTS dni VARCHAR(8);")
            cursor.execute("ALTER TABLE inventario_cliente ADD COLUMN IF NOT EXISTS ruc VARCHAR(11);")
            cursor.execute("ALTER TABLE inventario_cliente ADD COLUMN IF NOT EXISTS razon_social VARCHAR(200);")

            # --- 4. NUEVO: TABLAS PARA EL MÓDULO DE CAJA ---
            # Tabla Caja Diaria
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_cajadiaria (
                    id SERIAL PRIMARY KEY,
                    fecha_apertura TIMESTAMP WITH TIME ZONE NOT NULL,
                    fecha_cierre TIMESTAMP WITH TIME ZONE,
                    monto_inicial NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                    monto_final_sistema NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                    monto_final_real NUMERIC(10, 2),
                    diferencia NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                    estado VARCHAR(10) NOT NULL DEFAULT 'ABIERTA',
                    observaciones TEXT,
                    tienda_id INTEGER REFERENCES inventario_tienda(id) ON DELETE CASCADE,
                    usuario_apertura_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
                    usuario_cierre_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL
                );
            """)

            # Tabla Movimientos de Caja
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_movimientocaja (
                    id SERIAL PRIMARY KEY,
                    tipo VARCHAR(10) NOT NULL,
                    monto NUMERIC(10, 2) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    fecha TIMESTAMP WITH TIME ZONE NOT NULL,
                    caja_id INTEGER REFERENCES inventario_cajadiaria(id) ON DELETE CASCADE,
                    usuario_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL
                );
            """)
            # -----------------------------------------------

        print("Mantenimiento: Tablas sincronizadas correctamente.")
    except Exception as e:
        print(f"Error en mantenimiento: {e}")
        
    # Recolectar estáticos
    try:
        execute_from_command_line(['manage.py', 'collectstatic', '--noinput'])
    except:
        pass

mantenimiento_total()
app = application
