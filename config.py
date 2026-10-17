"""Configuracion de la aplicacion, leida exclusivamente de variables de entorno.

Ninguna credencial queda escrita en el codigo fuente: Elastic Beanstalk inyecta
estos valores como variables de entorno del entorno de ejecucion.
"""
import os


def _database_uri() -> str:
    """Construye la URI de PostgreSQL a partir de las variables de entorno.

    Si DATABASE_URL esta definida se usa tal cual (util para pruebas locales
    con SQLite). En AWS se arma con los datos del RDS.
    """
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit

    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "blacklist")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


class Config:
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Reciclar conexiones antes de que RDS las cierre por inactividad.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Token Bearer estatico/predefinido para toda la aplicacion, permitido
    # explicitamente por el enunciado de la entrega.
    STATIC_BEARER_TOKEN = os.environ.get("STATIC_BEARER_TOKEN", "")

    # Secreto usado por Flask-JWT-Extended cuando el token presentado es un JWT.
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", STATIC_BEARER_TOKEN or "cambieme")
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
