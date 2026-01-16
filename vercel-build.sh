# vercel-build.sh corregido
python3 -m pip install -r requirements.txt
python3 manage.py migrate --fake-initial --noinput
python3 manage.py collectstatic --noinput
