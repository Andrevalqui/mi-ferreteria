import os
from django.core.wsgi import get_wsgi_application
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

# --- SOLUCIÓN DEFINITIVA: INYECCIÓN SQL DIRECTA ---
def corregir_base_de_datos():
    try:
        with connection.cursor() as cursor:
            # Este comando agrega la columna directamente en Neon
            cursor.execute("""
                ALTER TABLE inventario_producto 
                ADD COLUMN IF NOT EXISTS unidad_medida VARCHAR(20) DEFAULT 'UND';
            """)
        print("Columna 'unidad_medida' verificada/creada con éxito.")
    except Exception as e:
        print(f"Nota: {e}")

corregir_base_de_datos()
# --------------------------------------------------

app = application
