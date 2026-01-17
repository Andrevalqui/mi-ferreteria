#!/bin/bash

echo "--- 1. INSTALANDO LIBRERIAS ---"
python3.12 -m pip install -r requirements.txt

echo "--- 2. RECOLECTANDO ESTATICOS (IMAGENES) ---"
# Esto crea la carpeta staticfiles que Vercel servirá
python3.12 manage.py collectstatic --noinput --clear

echo "--- 3. MIGRANDO BASE DE DATOS ---"
# Esto aplica los cambios a tu PostgreSQL de NeonDB/Vercel
python3.12 manage.py makemigrations
python3.12 manage.py migrate
