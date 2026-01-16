python3.9 -m pip install -r requirements.txt
python3.9 manage.py migrate --fake-initial --noinput
python3.9 manage.py collectstatic --noinput
