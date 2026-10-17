"""Autorizacion por Bearer Token.

El enunciado permite un token estatico/predefinido para toda la aplicacion.
Ese token se lee de la variable de entorno STATIC_BEARER_TOKEN. Si el token
presentado no es el estatico, se intenta validarlo como JWT con
Flask-JWT-Extended, de modo que el servicio tambien acepta tokens firmados.
"""
import hmac
from functools import wraps

from flask import current_app, request
from flask_jwt_extended import verify_jwt_in_request
from werkzeug.exceptions import Unauthorized


def presented_token() -> str | None:
    """Extrae el token del encabezado 'Authorization: Bearer <token>'."""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_bearer_token(view):
    """Exige un Bearer Token valido antes de ejecutar la vista."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        token = presented_token()
        if token is None:
            raise Unauthorized(
                description="Se requiere el encabezado 'Authorization: Bearer <token>'."
            )

        expected = current_app.config.get("STATIC_BEARER_TOKEN") or ""
        # Comparacion en tiempo constante para no filtrar el token por timing.
        if expected and hmac.compare_digest(token, expected):
            return view(*args, **kwargs)

        try:
            verify_jwt_in_request()
        except Exception:
            raise Unauthorized(description="Token de autorizacion invalido.") from None
        return view(*args, **kwargs)

    return wrapper
