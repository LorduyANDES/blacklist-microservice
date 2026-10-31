"""Recursos REST del microservicio de lista negra global."""
from datetime import datetime, timezone

from flask import request
from flask_restful import Resource
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from auth import require_bearer_token
from models import (
    BlacklistEntry,
    blacklist_create_schema,
    blacklist_entry_schema,
    db,
)


def _client_ip() -> str:
    """IP real del solicitante.

    ProxyFix ya resolvio X-Forwarded-For contando los saltos de confianza
    (ALB y nginx), por lo que este valor corresponde al cliente y no al proxy.
    """
    return request.remote_addr or "unknown"


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _find_by_email(email: str) -> BlacklistEntry | None:
    return db.session.execute(
        db.select(BlacklistEntry).filter_by(email=email)
    ).scalar_one_or_none()


class HealthResource(Resource):
    """Health check consumido por el balanceador de Elastic Beanstalk.

    Es una verificacion de vida deliberadamente liviana: no consulta la base de
    datos, para que una latencia puntual del RDS no saque de servicio a las
    instancias.
    """

    def get(self):
        return {
            "status": "ok",
            "service": "blacklist-microservice",
            "time": datetime.now(timezone.utc).isoformat(),
        }, 200


class BlacklistResource(Resource):
    """POST /blacklists - agrega un email a la lista negra global."""

    @require_bearer_token
    def post(self):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {
                "created": False,
                "message": "El cuerpo de la solicitud debe ser un objeto JSON.",
            }, 400

        try:
            data = blacklist_create_schema.load(payload)
        except ValidationError as err:
            return {
                "created": False,
                "message": "Los datos enviados no son validos.",
                "errors": err.messages,
            }, 400

        email = _normalize_email(data["email"])

        if _find_by_email(email) is not None:
            return {
                "created": False,
                "message": "El email ya se encuentra en la lista negra global.",
            }, 409

        entry = BlacklistEntry(
            email=email,
            app_uuid=str(data["app_uuid"]),
            blocked_reason=data.get("blocked_reason"),
            request_ip=_client_ip(),
        )
        db.session.add(entry)
        try:
            db.session.commit()
        except IntegrityError:
            # Dos solicitudes simultaneas para el mismo email: la restriccion
            # unica de la base de datos es la que decide.
            db.session.rollback()
            return {
                "created": False,
                "message": "El email ya se encuentra en la lista negra global.",
            }, 409

        return {
            "created": True,
            "message": "El email fue agregado a la lista negra global.",
            "data": blacklist_entry_schema.dump(entry),
        }, 201


class BlacklistEmailResource(Resource):
    """GET /blacklists/<email> - consulta si un email esta en la lista negra."""

    @require_bearer_token
    def get(self, email: str):
        normalized = _normalize_email(email)
        entry = _find_by_email(normalized)
        return {
            "email": normalized,
            "blacklisted": entry is not None,
            "blocked_reason": entry.blocked_reason if entry is not None else None,
        }, 200
