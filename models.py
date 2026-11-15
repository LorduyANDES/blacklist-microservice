"""Modelo de datos y esquemas de serializacion de la lista negra global."""
from datetime import datetime, timezone

from flask_marshmallow import Marshmallow
from flask_sqlalchemy import SQLAlchemy
from marshmallow import RAISE, fields, validate

db = SQLAlchemy()
ma = Marshmallow()

# Longitud maxima de un email segun RFC 5321.
EMAIL_MAX_LENGTH = 254
# Suficiente para una direccion IPv6 (45 caracteres).
IP_MAX_LENGTH = 45


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BlacklistEntry(db.Model):
    """Un email agregado a la lista negra global de la organizacion."""

    __tablename__ = "blacklist_entries"

    id = db.Column(db.Integer, primary_key=True)

    # Se almacena normalizado (minusculas, sin espacios) para que la consulta
    # por email sea deterministica.
    email = db.Column(db.String(EMAIL_MAX_LENGTH), nullable=False, unique=True, index=True)

    # UUID de la aplicacion cliente que solicito el bloqueo.
    app_uuid = db.Column(db.String(36), nullable=False)

    blocked_reason = db.Column(db.String(255), nullable=True)

    # Datos registrados internamente por el microservicio, no enviados por el cliente.
    request_ip = db.Column(db.String(IP_MAX_LENGTH), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuracion
        return f"<BlacklistEntry {self.id}>"


class BlacklistCreateSchema(ma.Schema):
    """Valida el cuerpo de la solicitud POST /blacklists.

    Solo acepta los tres campos del contrato: la IP y la fecha/hora las
    determina el servidor, nunca el cliente.
    """

    class Meta:
        # Un campo desconocido es un error explicito, no un valor ignorado.
        unknown = RAISE

    email = fields.Email(required=True, validate=validate.Length(max=EMAIL_MAX_LENGTH))
    app_uuid = fields.UUID(required=True)
    blocked_reason = fields.String(
        required=False,
        load_default=None,
        allow_none=True,
        validate=validate.Length(max=255),
    )


class BlacklistEntrySchema(ma.Schema):
    """Representacion de salida de una entrada de la lista negra."""

    id = fields.Integer(dump_only=True)
    email = fields.String(dump_only=True)
    app_uuid = fields.String(dump_only=True)
    blocked_reason = fields.String(dump_only=True, allow_none=True)
    request_ip = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


blacklist_create_schema = BlacklistCreateSchema()
blacklist_entry_schema = BlacklistEntrySchema()
