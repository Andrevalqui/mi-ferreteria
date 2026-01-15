# vercel-build.sh
python3.9 -m pip install -r requirements.txt
python3.9 manage.py migrate --noinput
python3.9 manage.py collectstatic --noinput