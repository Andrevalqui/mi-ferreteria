"""
Django settings for mi_erp project (Production Ready).
"""

from pathlib import Path
import os
import dj_database_url # Necesario para Vercel/Postgres

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
# En producción, usa una variable de entorno. Aquí hay un fallback.
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-z+fz$--(*9&!)6b47a)hn^2%8ekfdm*r7ih$mrj@u8y1!e0zd2')

# SECURITY WARNING: don't run with debug turned on in production!
# Vercel establece 'DEBUG' como False por defecto si no se especifica.
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# Permitir Vercel (.vercel.app) y localhost
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'inventario',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'import_export',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mi_erp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mi_erp.wsgi.application'

# Database configuration
# En local usa SQLite. En Vercel usa la variable DATABASE_URL (Postgres)
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///' + str(BASE_DIR / 'db.sqlite3'),
        conn_max_age=600
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-pe'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# AGREGA ESTA LÍNEA AQUÍ:
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage", # Quitamos 'Manifest' temporalmente para evitar errores
    },
}
# Media files (Carga de imágenes - OJO: Vercel no guarda esto permanentemente, usar S3/Cloudinary en el futuro)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'inventario:login'
LOGIN_REDIRECT_URL = 'inventario:dashboard'

LOGOUT_REDIRECT_URL = 'inventario:portal'




