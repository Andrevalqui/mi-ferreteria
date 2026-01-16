# vercel-build.sh
echo "--- INSTALANDO LIBRERIAS ---"
python3 -m pip install -r requirements.txt

echo "--- APLICANDO CAMBIOS EN BASE DE DATOS ---"
# Esto creará las tablas que te faltan (CajaDiaria, etc)
python3 manage.py makemigrations --noinput
python3 manage.py migrate --noinput

echo "--- RECOLECTANDO IMAGENES Y CSS ---"
# Esto hará que logo.jpeg y portada.jpeg vuelvan a aparecer
python3 manage.py collectstatic --noinput --clear
