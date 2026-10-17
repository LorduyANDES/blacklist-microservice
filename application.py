"""Punto de entrada del microservicio de lista negra global.

AWS Elastic Beanstalk busca por defecto un modulo llamado 'application' que
exponga una variable WSGI llamada 'application'. Ambos nombres son requisito
de la plataforma y no deben cambiarse.
"""
import logging
import os

from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_restful import Api
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from models import db, ma
from views import BlacklistEmailResource, BlacklistResource, HealthResource

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    """Respuestas de error siempre en JSON, nunca HTML."""

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"message": "Recurso no encontrado."}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({"message": "Metodo no permitido para este recurso."}), 405

    @app.errorhandler(500)
    def internal_error(_error):
        # No se incluye el detalle de la excepcion en la respuesta.
        return jsonify({"message": "Error interno del servidor."}), 500


def init_database(app: Flask) -> None:
    """Crea la tabla de la lista negra si aun no existe.

    Para esta primera iteracion no se usan migraciones: create_all es
    idempotente y suficiente. Si el RDS no esta disponible al arrancar se
    registra el error y la instancia sigue viva, de modo que el health check
    responde y el problema puede diagnosticarse desde los logs.
    """
    with app.app_context():
        try:
            db.create_all()
        except Exception as exc:  # pragma: no cover - depende de la red
            logger.error("No fue posible inicializar la base de datos: %s", exc)


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    if not app.config.get("STATIC_BEARER_TOKEN"):
        logger.warning(
            "STATIC_BEARER_TOKEN no esta definido: solo se aceptaran tokens JWT firmados."
        )

    # Detras del balanceador de Elastic Beanstalk, para que la IP registrada
    # sea la del cliente y no la del proxy.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    ma.init_app(app)
    JWTManager(app)

    api = Api(app)
    api.add_resource(HealthResource, "/")
    api.add_resource(BlacklistResource, "/blacklists")
    api.add_resource(BlacklistEmailResource, "/blacklists/<string:email>")

    register_error_handlers(app)
    init_database(app)
    return app


# Nombre exigido por AWS Elastic Beanstalk.
application = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    application.run(host="0.0.0.0", port=port, debug=False)
