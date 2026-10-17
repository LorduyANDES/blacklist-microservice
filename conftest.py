"""Configuracion compartida de las pruebas.

Las pruebas se ejecutan contra SQLite en un archivo temporal para validar la
logica del API sin depender de una instancia de PostgreSQL. El modelo usa
unicamente tipos portables, por lo que el comportamiento verificado aqui es el
mismo que en el RDS.
"""
import pytest

from application import create_app
from config import Config
from models import db

TEST_TOKEN = "token-de-pruebas-123"


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"

    class TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(db_path)
        SQLALCHEMY_ENGINE_OPTIONS: dict = {}
        STATIC_BEARER_TOKEN = TEST_TOKEN
        JWT_SECRET_KEY = "secreto-de-pruebas"
        TESTING = True

    application = create_app(TestConfig)
    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer " + TEST_TOKEN}
