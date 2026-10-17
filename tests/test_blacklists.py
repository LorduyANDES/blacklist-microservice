"""Pruebas del contrato del API de lista negra global."""
from models import BlacklistEntry, db

VALID_UUID = "3f0c1b9a-6d2e-4a1b-9c8d-5e7f2a1b3c4d"


def _payload(**overrides):
    body = {
        "email": "cliente@example.com",
        "app_uuid": VALID_UUID,
        "blocked_reason": "Solicitud del area legal",
    }
    body.update(overrides)
    return body


# --- Health check ---------------------------------------------------------

def test_health_check_responde_ok_sin_token(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


# --- Autorizacion ---------------------------------------------------------

def test_post_sin_encabezado_de_autorizacion_es_401(client):
    response = client.post("/blacklists", json=_payload())
    assert response.status_code == 401


def test_post_con_token_incorrecto_es_401(client):
    response = client.post(
        "/blacklists", json=_payload(), headers={"Authorization": "Bearer token-falso"}
    )
    assert response.status_code == 401


def test_post_con_esquema_no_bearer_es_401(client):
    response = client.post(
        "/blacklists", json=_payload(), headers={"Authorization": "Basic abc"}
    )
    assert response.status_code == 401


def test_get_sin_token_es_401(client):
    response = client.get("/blacklists/cliente@example.com")
    assert response.status_code == 401


# --- POST /blacklists -----------------------------------------------------

def test_post_valido_crea_la_entrada(client, auth_headers):
    response = client.post("/blacklists", json=_payload(), headers=auth_headers)
    assert response.status_code == 201
    body = response.get_json()
    assert body["created"] is True
    assert body["data"]["email"] == "cliente@example.com"
    assert body["data"]["blocked_reason"] == "Solicitud del area legal"


def test_post_registra_ip_y_fecha_internamente(app, client, auth_headers):
    client.post("/blacklists", json=_payload(), headers=auth_headers)
    with app.app_context():
        entry = db.session.execute(db.select(BlacklistEntry)).scalar_one()
        assert entry.request_ip
        assert entry.created_at is not None


def test_post_usa_la_ip_del_cliente_detras_del_balanceador(app, client, auth_headers):
    # Cadena real en Elastic Beanstalk: cliente -> ALB -> nginx. El ALB agrega
    # la IP del cliente y nginx agrega la del ALB, de modo que la del cliente
    # queda en la penultima posicion.
    headers = dict(auth_headers)
    headers["X-Forwarded-For"] = "203.0.113.45, 172.31.35.99"
    client.post("/blacklists", json=_payload(), headers=headers)
    with app.app_context():
        entry = db.session.execute(db.select(BlacklistEntry)).scalar_one()
        assert entry.request_ip == "203.0.113.45"


def test_no_se_puede_falsificar_la_ip_con_un_solo_salto(app, client, auth_headers):
    # Un cliente que inventa su propio X-Forwarded-For no alcanza los dos saltos
    # de confianza, asi que no logra suplantar la IP registrada.
    headers = dict(auth_headers)
    headers["X-Forwarded-For"] = "1.2.3.4"
    client.post("/blacklists", json=_payload(), headers=headers)
    with app.app_context():
        entry = db.session.execute(db.select(BlacklistEntry)).scalar_one()
        assert entry.request_ip != "1.2.3.4"


def test_blocked_reason_es_opcional(client, auth_headers):
    body = _payload()
    del body["blocked_reason"]
    response = client.post("/blacklists", json=body, headers=auth_headers)
    assert response.status_code == 201
    assert response.get_json()["data"]["blocked_reason"] is None


def test_email_duplicado_es_409(client, auth_headers):
    client.post("/blacklists", json=_payload(), headers=auth_headers)
    response = client.post("/blacklists", json=_payload(), headers=auth_headers)
    assert response.status_code == 409
    assert response.get_json()["created"] is False


def test_email_duplicado_con_otra_capitalizacion_es_409(client, auth_headers):
    client.post("/blacklists", json=_payload(), headers=auth_headers)
    response = client.post(
        "/blacklists", json=_payload(email="Cliente@Example.COM"), headers=auth_headers
    )
    assert response.status_code == 409


def test_email_invalido_es_400(client, auth_headers):
    response = client.post(
        "/blacklists", json=_payload(email="no-es-un-email"), headers=auth_headers
    )
    assert response.status_code == 400
    assert "email" in response.get_json()["errors"]


def test_email_faltante_es_400(client, auth_headers):
    body = _payload()
    del body["email"]
    response = client.post("/blacklists", json=body, headers=auth_headers)
    assert response.status_code == 400


def test_app_uuid_faltante_es_400(client, auth_headers):
    body = _payload()
    del body["app_uuid"]
    response = client.post("/blacklists", json=body, headers=auth_headers)
    assert response.status_code == 400
    assert "app_uuid" in response.get_json()["errors"]


def test_app_uuid_con_formato_invalido_es_400(client, auth_headers):
    response = client.post(
        "/blacklists", json=_payload(app_uuid="no-es-un-uuid"), headers=auth_headers
    )
    assert response.status_code == 400


def test_blocked_reason_de_mas_de_255_caracteres_es_400(client, auth_headers):
    response = client.post(
        "/blacklists", json=_payload(blocked_reason="x" * 256), headers=auth_headers
    )
    assert response.status_code == 400
    assert "blocked_reason" in response.get_json()["errors"]


def test_blocked_reason_de_exactamente_255_caracteres_es_valido(client, auth_headers):
    response = client.post(
        "/blacklists", json=_payload(blocked_reason="x" * 255), headers=auth_headers
    )
    assert response.status_code == 201


def test_campo_desconocido_es_400(client, auth_headers):
    response = client.post(
        "/blacklists", json=_payload(request_ip="1.2.3.4"), headers=auth_headers
    )
    assert response.status_code == 400


def test_cuerpo_que_no_es_json_es_400(client, auth_headers):
    headers = dict(auth_headers)
    headers["Content-Type"] = "text/plain"
    response = client.post("/blacklists", data="texto plano", headers=headers)
    assert response.status_code == 400


# --- GET /blacklists/<email> ---------------------------------------------

def test_get_email_en_lista_negra_retorna_true_y_motivo(client, auth_headers):
    client.post("/blacklists", json=_payload(), headers=auth_headers)
    response = client.get("/blacklists/cliente@example.com", headers=auth_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["blacklisted"] is True
    assert body["blocked_reason"] == "Solicitud del area legal"


def test_get_email_no_listado_retorna_false_y_motivo_nulo(client, auth_headers):
    response = client.get("/blacklists/otro@example.com", headers=auth_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["blacklisted"] is False
    assert body["blocked_reason"] is None


def test_get_es_insensible_a_la_capitalizacion(client, auth_headers):
    client.post("/blacklists", json=_payload(), headers=auth_headers)
    response = client.get("/blacklists/CLIENTE@EXAMPLE.COM", headers=auth_headers)
    assert response.get_json()["blacklisted"] is True


def test_get_de_email_sin_motivo_retorna_motivo_nulo(client, auth_headers):
    body = _payload()
    del body["blocked_reason"]
    client.post("/blacklists", json=body, headers=auth_headers)
    response = client.get("/blacklists/cliente@example.com", headers=auth_headers)
    assert response.get_json() == {
        "email": "cliente@example.com",
        "blacklisted": True,
        "blocked_reason": None,
    }


# --- Errores generales ----------------------------------------------------

def test_ruta_inexistente_responde_json(client):
    response = client.get("/no-existe")
    assert response.status_code == 404
    assert response.is_json
