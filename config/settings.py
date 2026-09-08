from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

from estoque.data_corte import parse_data_corte
from config.database import resolve_database

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DEV_SECRET_KEY = "dev-only-not-for-production"


def parse_env_bool(value):
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized == "":
        return None
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f"Invalid boolean environment value: {value!r}. "
        "Use true/false, 1/0, yes/no or on/off."
    )


def is_production_environment(environ):
    raw = environ.get("DJANGO_ENVIRONMENT")
    if raw is None or not str(raw).strip():
        return False
    return str(raw).strip().lower() in {"production", "prod"}


def resolve_debug(environ):
    """
    DEBUG explícito via DJANGO_DEBUG (true/false, 1/0, yes/no, on/off).

    Se DJANGO_DEBUG estiver ausente:
      - desenvolvimento → True (runserver local)
      - produção (DJANGO_ENVIRONMENT=production|prod) → False
    """
    parsed = parse_env_bool(environ.get("DJANGO_DEBUG"))
    if parsed is not None:
        return parsed
    return not is_production_environment(environ)


def resolve_secret_key(environ, *, debug, production):
    """
    SECRET_KEY só pode ter fallback no desenvolvimento com DEBUG=True.
    Produção ou DEBUG=False exigem DJANGO_SECRET_KEY no ambiente.
    """
    raw = environ.get("DJANGO_SECRET_KEY")
    secret = str(raw).strip() if raw is not None else ""
    if secret:
        return secret
    if production or not debug:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is required when DEBUG is false "
            "or DJANGO_ENVIRONMENT is production."
        )
    return _DEV_SECRET_KEY


# ============================================================
# SECURITY
# ============================================================
# Desenvolvimento local (runserver sem variáveis):
#   DJANGO_ENVIRONMENT omitido ou development
#   DJANGO_DEBUG omitido ou true
# Produção:
#   DJANGO_ENVIRONMENT=production
#   DJANGO_DEBUG=false
#   DJANGO_SECRET_KEY=<chave forte do ambiente>
#   DJANGO_ALLOWED_HOSTS=dominio.exemplo

_PRODUCTION = is_production_environment(os.environ)
DEBUG = resolve_debug(os.environ)
SECRET_KEY = resolve_secret_key(
    os.environ,
    debug=DEBUG,
    production=_PRODUCTION,
)

ALLOWED_HOSTS = _env_list(
    "DJANGO_ALLOWED_HOSTS",
    ["localhost", "127.0.0.1"],
)

CSRF_TRUSTED_ORIGINS = _env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    [],
)


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [
    "core.admin_config.GelosarAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core",
    "accounts",
    "equipamentos",
    "produtos",
    "insumos",
    "estoque",
    "producao",
    "clientes",
    "vendas",
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL / WSGI
# ============================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates",
        ],

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


# ============================================================
# DATABASE
# ============================================================
# Desenvolvimento (sem DATABASE_URL): SQLite em db.sqlite3.
# Produção: DATABASE_URL PostgreSQL obrigatória (ex. Railway).
# CONN_MAX_AGE: 0 no SQLite; 60 no PostgreSQL, ou DJANGO_CONN_MAX_AGE.
# SSL: query sslmode= na URL ou DJANGO_DATABASE_SSLMODE (só PostgreSQL).

DATABASES = resolve_database(
    os.environ,
    production=_PRODUCTION,
    base_dir=BASE_DIR,
)


# ============================================================
# PASSWORD VALIDATION
# ============================================================

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


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = "pt-br"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

# Manifest + compressão só em produção (DEBUG=False). Em desenvolvimento
# o Manifest exige staticfiles/ já coletado e quebra templates/testes.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

# chart.umd.min.js referencia um .map que não está no repositório.
# Sem isto o collectstatic em produção (Manifest) falha no Railway.
WHITENOISE_MANIFEST_STRICT = False


# ============================================================
# MEDIA FILES
# ============================================================
# Arquivos de documentos NÃO são servidos publicamente por /media/.
# O download autenticado ocorre em equipamentos:download_documento.

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ============================================================
# AUTHENTICATION
# ============================================================

LOGIN_URL = "/login/"

LOGIN_REDIRECT_URL = "/dashboard/"

LOGOUT_REDIRECT_URL = "/login/"


# ============================================================
# HTTPS / COOKIES (somente produção)
# ============================================================

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False


# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# ESTOQUE — DATA DE CORTE (opcional)
# ============================================================
# Variável: DJANGO_ESTOQUE_DATA_CORTE=YYYY-MM-DD
#
# Política de implantação (intencional, não é erro de configuração):
#   Ausente ou vazio → ESTOQUE_DATA_CORTE = None
#     → vendas NÃO geram SAIDA automática
#     → produção continua gerando ENTRADA (fluxo independente)
#     → não há backfill ao definir a data depois
#   Definida → SAIDA automática só se venda.data >= data de corte
#     (igualdade inclusiva; ver estoque.services.venda_deve_gerar_saida)
# Valor inválido → ImproperlyConfigured na inicialização.
# Não definir data fixa no código. A data de negócio é decisão operacional.

ESTOQUE_DATA_CORTE = parse_data_corte(
    os.environ.get("DJANGO_ESTOQUE_DATA_CORTE")
)
