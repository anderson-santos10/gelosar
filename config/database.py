"""Resolução de DATABASES a partir do ambiente (SQLite local / PostgreSQL)."""

from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

SQLITE_ENGINE = "django.db.backends.sqlite3"
POSTGRES_ENGINE = "django.db.backends.postgresql"

# Conexões persistentes só no PostgreSQL. 60s é o ponto de partida
# da documentação do Django para CONN_MAX_AGE em produção.
POSTGRES_CONN_MAX_AGE_PADRAO = 60


def parse_database_url(url):
    if not url or not str(url).strip():
        raise ImproperlyConfigured("DATABASE_URL vazia.")
    parsed = urlparse(str(url).strip())
    scheme = (parsed.scheme or "").lower()
    if scheme in {"postgres", "postgresql", "pgsql"}:
        nome = unquote((parsed.path or "").lstrip("/"))
        if not nome:
            raise ImproperlyConfigured("DATABASE_URL PostgreSQL sem nome de banco.")
        config = {
            "ENGINE": POSTGRES_ENGINE,
            "NAME": nome,
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": unquote(parsed.hostname or ""),
            "PORT": str(parsed.port or "5432"),
        }
        query = parse_qs(parsed.query)
        if "sslmode" in query and query["sslmode"]:
            config["OPTIONS"] = {"sslmode": query["sslmode"][0]}
        return config
    if scheme in {"sqlite", "sqlite3"}:
        path = unquote(parsed.path or "")
        if parsed.netloc and path:
            path = f"/{parsed.netloc}{path}"
        if not path or path == "/":
            raise ImproperlyConfigured("DATABASE_URL SQLite sem caminho.")
        return {
            "ENGINE": SQLITE_ENGINE,
            "NAME": path,
        }
    raise ImproperlyConfigured(
        f"Esquema de DATABASE_URL não suportado: {scheme!r}."
    )


def _conn_max_age(config, environ):
    raw = environ.get("DJANGO_CONN_MAX_AGE")
    if raw is not None and str(raw).strip() != "":
        try:
            return int(str(raw).strip())
        except ValueError as exc:
            raise ImproperlyConfigured(
                "DJANGO_CONN_MAX_AGE deve ser um inteiro."
            ) from exc
    if config.get("ENGINE") == POSTGRES_ENGINE:
        return POSTGRES_CONN_MAX_AGE_PADRAO
    return 0


def _aplicar_sslmode_env(config, environ):
    if config.get("ENGINE") != POSTGRES_ENGINE:
        return config
    sslmode = (environ.get("DJANGO_DATABASE_SSLMODE") or "").strip()
    if not sslmode:
        return config
    options = dict(config.get("OPTIONS") or {})
    options.setdefault("sslmode", sslmode)
    atualizado = dict(config)
    atualizado["OPTIONS"] = options
    return atualizado


def sqlite_local(base_dir):
    return {
        "ENGINE": SQLITE_ENGINE,
        "NAME": Path(base_dir) / "db.sqlite3",
        "CONN_MAX_AGE": 0,
    }


def resolve_database(environ, *, production, base_dir):
    """
    Desenvolvimento: SQLite em db.sqlite3, a menos que DATABASE_URL exista.
    Produção: DATABASE_URL PostgreSQL obrigatória. SQLite é recusado.
    """
    url = (environ.get("DATABASE_URL") or "").strip()
    if url:
        config = parse_database_url(url)
    elif production:
        raise ImproperlyConfigured(
            "DATABASE_URL is required when DJANGO_ENVIRONMENT is production."
        )
    else:
        config = sqlite_local(base_dir)

    config = _aplicar_sslmode_env(config, environ)
    config = dict(config)
    config["CONN_MAX_AGE"] = _conn_max_age(config, environ)

    if production and config.get("ENGINE") == SQLITE_ENGINE:
        raise ImproperlyConfigured(
            "SQLite is not allowed when DJANGO_ENVIRONMENT is production. "
            "Set DATABASE_URL to a PostgreSQL connection."
        )
    return {"default": config}
