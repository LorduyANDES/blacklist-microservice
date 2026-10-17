# Microservicio de Lista Negra Global de Emails

Entrega 1 — Despliegue manual de un microservicio sobre un servicio de Plataforma como Servicio (PaaS).
Curso de Cloud Computing, Universidad de los Andes.

Microservicio REST centralizado que permite a cientos de sistemas internos consultar si un email
está en la lista negra global de la organización, así como agregar emails a esa lista.

## Stack tecnológico

| Componente | Uso en el proyecto |
|---|---|
| Python 3.13 | Lenguaje de programación |
| Flask | Micro framework web |
| Flask-SQLAlchemy | ORM sobre PostgreSQL |
| Flask-RESTful | Recursos REST orientados a objetos |
| Flask-Marshmallow | Validación y serialización de entrada/salida |
| Flask-JWT-Extended | Validación de tokens Bearer |
| Werkzeug | Capa WSGI y `ProxyFix` detrás del balanceador |
| PostgreSQL (AWS RDS) | Persistencia |
| Gunicorn | Servidor WSGI en producción |

## API REST

Todos los endpoints de negocio exigen el encabezado `Authorization: Bearer <token>`.

### `GET /` — Health check

Verificación de vida consumida por el health check de Elastic Beanstalk. Público, no requiere token.
Es deliberadamente liviano: no consulta la base de datos, para que una latencia puntual del RDS no
saque de servicio a las instancias.

```json
{ "status": "ok", "service": "blacklist-microservice", "time": "2026-10-17T15:21:22.354718+00:00" }
```

### `POST /blacklists` — Agregar un email a la lista negra global

| Campo | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `email` | String | Sí | Formato de email válido, máximo 254 caracteres |
| `app_uuid` | String | Sí | UUID válido de la app cliente |
| `blocked_reason` | String | No | Máximo 255 caracteres |

La **dirección IP** desde donde se hace la solicitud y la **fecha/hora** de la misma se registran
internamente por el microservicio. No se aceptan como parámetros de entrada: un cuerpo que los
incluya se rechaza con 400.

```bash
curl -X POST "$BASE_URL/blacklists" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"email":"spam@example.com","app_uuid":"3f0c1b9a-6d2e-4a1b-9c8d-5e7f2a1b3c4d","blocked_reason":"Reportado por abuso"}'
```

| Código | Significado |
|---|---|
| 201 | El email fue agregado (`created: true`) |
| 400 | Datos inválidos; el detalle viene en `errors` |
| 401 | Token ausente o inválido |
| 409 | El email ya estaba en la lista negra global (`created: false`) |

### `GET /blacklists/<email>` — Consultar si un email está en la lista negra

Retorna un booleano y el motivo por el que fue agregado. La consulta es insensible a mayúsculas y
minúsculas. Un email no listado responde **200 con `blacklisted: false`**, no 404: la consulta es
exitosa y su resultado es negativo.

```bash
curl "$BASE_URL/blacklists/spam@example.com" -H "Authorization: Bearer $TOKEN"
```

```json
{ "email": "spam@example.com", "blacklisted": true, "blocked_reason": "Reportado por abuso" }
```

## Autorización

El enunciado permite definir el token Bearer de forma estática o predefinida para toda la
aplicación. Ese token se lee de la variable de entorno `STATIC_BEARER_TOKEN` y **nunca está escrito
en el código fuente**. La comparación se hace en tiempo constante (`hmac.compare_digest`) para no
filtrar el token por diferencias de tiempo de respuesta.

Si el token presentado no es el estático, se intenta validarlo como JWT firmado con
Flask-JWT-Extended, de modo que el servicio también acepta tokens dinámicos sin cambios de código.

## Variables de entorno

| Variable | Descripción |
|---|---|
| `DB_USER` | Usuario de PostgreSQL |
| `DB_PASSWORD` | Contraseña de PostgreSQL |
| `DB_HOST` | Endpoint del RDS |
| `DB_PORT` | Puerto de PostgreSQL (5432) |
| `DB_NAME` | Nombre de la base de datos |
| `STATIC_BEARER_TOKEN` | Token Bearer que deben presentar los clientes |
| `DATABASE_URL` | Opcional. Si está definida, reemplaza a las anteriores (útil para pruebas locales) |

`.env.example` documenta el formato. `.env` está excluido del repositorio: **no se versionan
credenciales**.

## Ejecución local

```bash
python -m venv venv
venv/Scripts/activate            # Linux/macOS: source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env             # y ajuste los valores
python application.py
```

El servicio queda en `http://127.0.0.1:5000`.

## Pruebas

```bash
python -m pytest -q
```

24 pruebas cubren el contrato completo: health check, autorización (token ausente, token
incorrecto, esquema no Bearer), validaciones de cada campo, duplicados, normalización de emails,
registro interno de IP y fecha/hora, y respuestas de error en JSON.

Las pruebas corren contra SQLite en un archivo temporal. El modelo usa únicamente tipos portables,
por lo que el comportamiento verificado es el mismo que en el RDS.

## Escenarios de prueba en Postman

La carpeta `postman/` contiene la colección y el environment exportados:

- `blacklist-microservice.postman_collection.json` — 13 escenarios con aserciones automáticas
- `blacklist-microservice.postman_environment.json` — variables `base_url`, `bearer_token`, `email_limpio`

Importe ambos archivos en Postman, complete `base_url` con la URL del entorno de Beanstalk y
`bearer_token` con el valor de `STATIC_BEARER_TOKEN`. La colección es autosuficiente: puede
ejecutarse de corrido con el Collection Runner, porque los escenarios de consulta y de duplicado
reutilizan el email que crea el escenario `01`.

> `bearer_token` se exporta vacío a propósito, para no versionar el secreto.

## Despliegue en AWS

### 1. RDS PostgreSQL

Instancia PostgreSQL en la misma VPC y región del entorno de Beanstalk. El grupo de seguridad del
RDS debe permitir el puerto 5432 **únicamente** desde el grupo de seguridad de las instancias EC2
del entorno, no desde `0.0.0.0/0`.

### 2. Elastic Beanstalk

Plataforma Python. La plataforma espera exactamente estos dos nombres, que por eso no deben
cambiarse:

- el módulo principal se llama `application.py`;
- la variable WSGI se llama `application`.

Archivos que consume la plataforma:

- `requirements.txt` — dependencias instaladas en cada instancia
- `Procfile` — comando Gunicorn que sirve la aplicación en el puerto 8000
- `.ebextensions/01_packages.config` — paquetes del sistema (`libpq-devel`, `gcc`)

### 3. Variables de entorno del entorno

Configure en Beanstalk `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` y
`STATIC_BEARER_TOKEN`. La tabla `blacklist_entries` se crea automáticamente en el primer arranque.

### 4. Health check

Ruta `/`, que responde 200 con JSON.

## Estructura del proyecto

```
application.py                 Punto de entrada WSGI exigido por Beanstalk
config.py                      Configuración leída de variables de entorno
models.py                      Modelo SQLAlchemy y esquemas Marshmallow
auth.py                        Autorización por Bearer Token
views.py                       Recursos REST (Flask-RESTful)
conftest.py                    Fixtures de pruebas
tests/test_blacklists.py       Pruebas del contrato del API
requirements.txt               Dependencias de ejecución
requirements-dev.txt           Dependencias de ejecución + pruebas
Procfile                       Comando de arranque en Beanstalk
.ebextensions/01_packages.config   Paquetes del sistema
postman/                       Colección y environment de Postman
```
