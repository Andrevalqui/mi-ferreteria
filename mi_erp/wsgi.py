import os
from django.core.wsgi import get_wsgi_application
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_erp.settings')

application = get_wsgi_application()

# --- REPARACIÓN DE BASE DE DATOS ---
def corregir_db():
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE inventario_producto 
                ADD COLUMN IF NOT EXISTS unidad_medida VARCHAR(20) DEFAULT 'UND';
            """)
    except Exception as e:
        print(f"Log: {e}")

corregir_db()
# ----------------------------------

app = application
