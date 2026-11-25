from pathlib import Path
# Workaround para MariaDB 10.4 (XAMPP): Django 5.2 exige >=10.5.
# Se desactiva la verificacion de version y RETURNING (no soportado en 10.4).
try:
    from django.db.backends.mysql.base import DatabaseWrapper as _MySQLWrapper
    _MySQLWrapper.check_database_version_supported = lambda self: None

    from django.db.backends.mysql.features import DatabaseFeatures
    DatabaseFeatures.can_return_columns_from_insert = property(lambda self: False)
except Exception:
    pass
from datetime import timedelta
import os
import sys


BASE_DIR = Path(__file__).resolve().parent.parent

# SECRET_KEY desde variable de entorno. El valor actual queda como fallback
# para no romper el arranque en producción (Passenger, sin vars de entorno).
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-f3rspg00ww-04u#iqia2tsj*@3kaziq%qk*np50z=)s*viwxcs",
)

# DEBUG por variable de entorno. Por defecto False (seguro): para desarrollo
# local hay que exportar DJANGO_DEBUG=true (o 1/yes/on).
DEBUG = os.environ.get("DJANGO_DEBUG", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


# ALLOWED_HOSTS por variable de entorno (comma-separated) o lista por defecto.
_allowed = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()] if _allowed else [
    "siaem.tamep.bo",
    "www.siaem.tamep.bo",
    "localhost",
    "127.0.0.1",
    "192.168.3.232",
    "192.168.1.241",
    "11.0.3.225",
    "testserver",
    ".onrender.com",
]

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# Claves de prueba oficiales de Cloudflare (siempre pasan; ver
# https://developers.cloudflare.com/turnstile/troubleshooting/testing/).
# Se sobreescriben por variables de entorno para producción.
# Claves de prueba oficiales de Cloudflare (siempre pasan; ver
# https://developers.cloudflare.com/turnstile/troubleshooting/testing/).
# En producción se sobreescriben por variables de entorno (TURNSTILE_SITE_KEY /
# TURNSTILE_SECRET_KEY). NO commitear claves reales aquí.
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA")

# Los tests no deben depender de la red: `manage.py test` desactiva Turnstile.
_TURNSTILE_TEST_RUN = "test" in sys.argv
TURNSTILE_ENABLED = (
    not _TURNSTILE_TEST_RUN
    and os.environ.get("TURNSTILE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
)

# --- 3. SEGURIDAD HTTPS (Crucial para cPanel) ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # True en el servidor
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False
_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()] if _cors else [
    "https://siaem.tamep.bo",
    "http://localhost:8080",
    "http://192.168.3.232:8080",
    "http://192.168.1.241:8080",
    "http://192.168.1.241:3000",
    "https://192.168.1.241:3443",
    "http://11.0.3.225:8080",
    "http://11.0.3.225:3000",
    "https://11.0.3.225:3443",
    "http://localhost:3000",
    "https://localhost:3443",
]

_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf.split(",") if o.strip()] if _csrf else [
    "https://siaem.tamep.bo",
]

INSTALLED_APPS = [
    "smart_selects",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "activos",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "activosfijosdb"),
        "USER": os.environ.get("DB_USER", "root"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "ssl": {"disabled": os.environ.get("DB_SSL_DISABLED", "false").lower() == "true"},
        },
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=180),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "es-es"

TIME_ZONE = "America/La_Paz"

USE_I18N = True

USE_TZ = True

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
STATIC_ROOT = os.path.join(BASE_DIR, "static_collected")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    # Paginación por defecto para listas/tablas (50 por página, ?page_size=N
    # con tope de 100). Los viewsets que alimentan dropdowns o que el
    # frontend consume como array plano usan pagination_class = None
    # (ver activos/views/*.py).
    "DEFAULT_PAGINATION_CLASS": "activos.views.paginacion.PaginacionEstandar",
    "PAGE_SIZE": 50,
    # Throttling por scope en los endpoints de autenticación (ScopedRateThrottle
    # en activos/views/auth.py). Valores pensados para una oficina institucional
    # con posible NAT compartido: login 20/min, register 10/hora, refresh 30/min.
    "DEFAULT_THROTTLE_RATES": {
        "login": "20/min",
        "register": "10/hour",
        "refresh": "30/min",
    },
    # Mensaje de 429 (throttling) en español; el resto delega al handler nativo.
    "EXCEPTION_HANDLER": "activos.views.auth.manejar_throttling",
}


USE_DJANGO_JQUERY = True
STATIC_URL = "/static/"
BASE_URL = "http://11.0.3.225:8000"
