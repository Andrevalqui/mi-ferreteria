# vercel-build.sh
python3 -m pip install -r requirements.txt

# Generamos las migraciones por si acaso faltó algo
python3 manage.py makemigrations --noinput

# Ejecutamos las migraciones REALES (sin el --fake-initial)
python3 manage.py migrate --noinput

# Recolectamos archivos estáticos
python3 manage.py collectstatic --noinput
