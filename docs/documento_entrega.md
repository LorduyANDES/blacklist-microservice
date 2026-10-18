# Proyecto 1 — Entrega 1
## Despliegue manual de un microservicio sobre un servicio de Plataforma como Servicio (PaaS)

**Curso:** Cloud Computing
**Universidad de los Andes**

**Autor:** Jesús Daniel Lorduy — j.lorduy@uniandes.edu.co

> `[COMPLETAR]` Integrantes del equipo. El enunciado indica que la actividad se
> realiza en equipo; agregue aquí nombre y correo de cada integrante.
>
> | Nombre | Correo |
> |---|---|
> | Jesús Daniel Lorduy | j.lorduy@uniandes.edu.co |
> | `[COMPLETAR]` | `[COMPLETAR]` |

**Fecha:** 18 de octubre de 2026

---

## Enlaces de la entrega

| Recurso | Enlace |
|---|---|
| Repositorio GitHub | https://github.com/LorduyANDES/blacklist-microservice |
| Aplicación desplegada | http://blacklist-env.eba-zgnk2x3x.us-east-2.elasticbeanstalk.com |
| Documentación publicada de Postman | `[COMPLETAR: URL publicada de la colección]` |
| Video de sustentación | `[COMPLETAR: URL del video, máximo 10 minutos]` |

---

## 1. Alcance de la solución

Se desarrolló y desplegó un microservicio REST que gestiona la **lista negra global
de emails** de una compañía multinacional. El objetivo es que cientos de sistemas
internos puedan consultar si un email está en la lista negra global, así como agregar
emails a ella, desde un servicio centralizado.

El microservicio expone dos operaciones de negocio y un health check, todas sobre un
único servicio, y persiste la información en una base de datos relacional
administrada (AWS RDS PostgreSQL).

---

## 2. Stack tecnológico

Se utilizó el stack exigido por el enunciado:

| Componente | Versión | Uso en el proyecto |
|---|---|---|
| Python | 3.13 | Lenguaje de programación |
| Flask | 3.1.0 | Micro framework web |
| Flask-SQLAlchemy | 3.1.1 | ORM sobre PostgreSQL |
| Flask-RESTful | 0.3.10 | Recursos REST orientados a objetos |
| Flask-Marshmallow | 1.3.0 | Validación y serialización |
| Flask-JWT-Extended | 4.7.1 | Validación de tokens Bearer |
| Werkzeug | 3.1.3 | Capa WSGI y `ProxyFix` tras el balanceador |
| PostgreSQL | 16.15 | Motor de base de datos (AWS RDS) |
| Gunicorn | 23.0.0 | Servidor WSGI en producción |

---

## 3. Diseño del API REST

### 3.1 `POST /blacklists`

Agrega un email a la lista negra global.

| Parámetro | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `email` | String | Sí | Formato válido, máximo 254 caracteres |
| `app_uuid` | String | Sí | UUID válido de la app cliente |
| `blocked_reason` | String | No | Máximo 255 caracteres |

**Autorización:** `Authorization: Bearer <token>`

La **dirección IP** del solicitante y la **fecha/hora** de la solicitud se registran
internamente y **no se aceptan como parámetros de entrada**: un cuerpo que los incluya
se rechaza con 400.

| Código | Significado |
|---|---|
| 201 | Email agregado (`created: true`) |
| 400 | Datos inválidos, con detalle en `errors` |
| 401 | Token ausente o inválido |
| 409 | El email ya estaba en la lista negra |

Ejemplo de respuesta 201:

```json
{
  "created": true,
  "message": "El email fue agregado a la lista negra global.",
  "data": {
    "id": 1,
    "email": "spam@example.com",
    "app_uuid": "3f0c1b9a-6d2e-4a1b-9c8d-5e7f2a1b3c4d",
    "blocked_reason": "Reportado por abuso",
    "request_ip": "186.29.120.221",
    "created_at": "2026-10-17T16:40:09.285374+00:00"
  }
}
```

### 3.2 `GET /blacklists/<email>`

Consulta si un email está en la lista negra global y el motivo por el que fue agregado.
La consulta es insensible a mayúsculas y minúsculas.

**Autorización:** `Authorization: Bearer <token>`

Un email no listado responde **200 con `blacklisted: false`**, no 404: la consulta es
exitosa y su resultado es negativo.

```json
{ "email": "spam@example.com", "blacklisted": true, "blocked_reason": "Reportado por abuso" }
```

### 3.3 `GET /` — Health check

Verificación de vida consumida por el balanceador de Elastic Beanstalk. Es público y
deliberadamente liviano: no consulta la base de datos, para que una latencia puntual
del RDS no saque de servicio a las instancias.

### 3.4 Autorización

El enunciado permite definir el token Bearer de forma estática o predefinida para toda
la aplicación. Ese token se lee de la variable de entorno `STATIC_BEARER_TOKEN` y
**nunca está escrito en el código fuente**. La comparación se hace en tiempo constante
(`hmac.compare_digest`) para no filtrar el token por diferencias de tiempo de respuesta.

---

## 4. Repositorio en GitHub

**URL:** https://github.com/LorduyANDES/blacklist-microservice

> 📸 **[CAPTURA 1]** — Página principal del repositorio en GitHub, mostrando la lista
> de archivos y el README.

> 📸 **[CAPTURA 2]** — Historial de commits (pestaña *Commits*), evidenciando el
> versionamiento del proyecto.

Estructura del repositorio:

```
application.py                   Punto de entrada WSGI exigido por Beanstalk
config.py                        Configuración leída de variables de entorno
models.py                        Modelo SQLAlchemy y esquemas Marshmallow
auth.py                          Autorización por Bearer Token
views.py                         Recursos REST (Flask-RESTful)
conftest.py                      Fixtures de pruebas
tests/test_blacklists.py         25 pruebas del contrato del API
requirements.txt                 Dependencias de ejecución
Procfile                         Comando Gunicorn de arranque
.ebextensions/01_packages.config Opciones de plataforma
postman/                         Colección y environment de Postman
docs/                            Documentación de la entrega
```

**Nota sobre seguridad:** el archivo `.env`, que contiene el token Bearer y la
contraseña del RDS, está excluido mediante `.gitignore` y **nunca fue versionado**. Se
verificó que ningún commit del historial contiene credenciales.

---

## 5. Configuración de AWS

### 5.1 Configuración de RDS

> 📸 **[CAPTURA 3]** — Consola de RDS mostrando la instancia `blacklist-db` con estado
> *Available*.

> 📸 **[CAPTURA 4]** — Pestaña *Connectivity & security* de la instancia, donde se vea
> **Publicly accessible: No** y el VPC security group asociado.

> 📸 **[CAPTURA 5]** — Reglas de entrada del security group del RDS, mostrando que el
> puerto 5432 solo acepta tráfico desde el security group de las instancias de
> Beanstalk, **no desde `0.0.0.0/0`**.

| Parámetro | Valor |
|---|---|
| Identificador | `blacklist-db` |
| Motor | PostgreSQL 16.15 |
| Clase de instancia | `db.t3.micro` |
| Almacenamiento | 20 GB, tipo gp3 |
| Base de datos | `blacklist` |
| Usuario maestro | `postgres` |
| Puerto | 5432 |
| Zona de disponibilidad | us-east-2a |
| Multi-AZ | No |
| **Acceso público** | **No** |
| Endpoint | `blacklist-db.XXXXXXXX.us-east-2.rds.amazonaws.com` |

> El endpoint completo se omite de este documento público por higiene de seguridad;
> el valor real está en el archivo local `.env` y en las variables de entorno del
> entorno de Beanstalk.

**Decisión de diseño:** la base de datos **no es accesible desde internet**. Su grupo
de seguridad permite el puerto 5432 **únicamente** desde el grupo de seguridad de las
instancias EC2 del entorno de Beanstalk. Esto reduce la superficie de exposición: aun
si las credenciales se filtraran, la base de datos no sería alcanzable desde fuera de
la VPC.

### 5.2 Configuración del proyecto en AWS Elastic Beanstalk

> 📸 **[CAPTURA 6]** — Página del entorno `blacklist-env` mostrando *Health: Ok*
> (verde), el dominio y la versión desplegada.

> 📸 **[CAPTURA 7]** — *Configuración → Instancias*, mostrando el tipo de instancia
> `t3.micro`.

> 📸 **[CAPTURA 8]** — *Configuración → Capacidad*, mostrando el grupo de autoescalado
> con **mínimo 3 y máximo 6** instancias y el tipo de entorno con balanceador.

> 📸 **[CAPTURA 9]** — *Configuración → Propiedades del entorno*, mostrando las
> variables `DB_USER`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_PASSWORD` y
> `STATIC_BEARER_TOKEN`.
> **Oculte los valores de `DB_PASSWORD` y `STATIC_BEARER_TOKEN` antes de capturar.**

| Parámetro | Valor |
|---|---|
| Aplicación | `blacklist-microservice` |
| Entorno | `blacklist-env` |
| ID del entorno | `e-tmjacz9vtk` |
| Región | us-east-2 (Ohio) |
| Plataforma | Python 3.13 sobre 64bit Amazon Linux 2023 / 4.13.10 |
| Tipo de entorno | Con balanceador (Application Load Balancer) |
| Tipo de instancia | `t3.micro` |
| Autoescalado | Mínimo 3, máximo 6 |
| URL | http://blacklist-env.eba-zgnk2x3x.us-east-2.elasticbeanstalk.com |

**Requisitos de la plataforma.** Elastic Beanstalk exige que el módulo principal se
llame `application.py` y que la variable WSGI se llame `application`; por eso esos
nombres no pueden cambiarse. El arranque se define en el `Procfile`:

```
web: gunicorn --bind 0.0.0.0:8000 --workers 3 --threads 2 --timeout 60 application:application
```

### 5.3 Configuración de los health checks

> 📸 **[CAPTURA 10]** — *Configuración → Supervisión*, mostrando la ruta del health
> check configurada en `/`.

> 📸 **[CAPTURA 11]** — Pestaña *Estado y supervisión* del entorno, mostrando las 3
> instancias en estado *Ok*.

| Parámetro | Valor |
|---|---|
| Ruta del health check | `/` |
| Código HTTP esperado | 200 |
| Tipo de reporte de salud | Enhanced |

El endpoint `/` responde 200 con un JSON de estado. Se eligió deliberadamente que
**no consulte la base de datos**: si el RDS tuviera una latencia puntual, un health
check dependiente de la base sacaría de servicio a instancias que en realidad están
sanas, provocando un reemplazo en cascada.

Esa ruta se fija además desde el repositorio, en
`.ebextensions/01_packages.config`, de modo que la configuración viaja con el código y
no depende de ajustes manuales en la consola.

---

## 6. Documentación y escenarios de prueba en Postman

**URL de la documentación publicada:** `[COMPLETAR]`

> 📸 **[CAPTURA 12]** — Colección de Postman abierta, mostrando la lista de escenarios.

> 📸 **[CAPTURA 13]** — Ejecución del *Collection Runner* con los escenarios en verde.

> 📸 **[CAPTURA 14]** — Ejemplo de solicitud y respuesta de `POST /blacklists` (201).

> 📸 **[CAPTURA 15]** — Ejemplo de solicitud y respuesta de `GET /blacklists/<email>`.

La colección y el environment están versionados en el repositorio, en la carpeta
`postman/`. La colección es autosuficiente: puede ejecutarse de corrido con el
Collection Runner, porque los escenarios de consulta y de duplicado reutilizan el email
que crea el escenario `01`.

Escenarios incluidos:

| # | Escenario | Resultado esperado |
|---|---|---|
| 00 | Health check `GET /` | 200 |
| 01 | Alta exitosa | 201 |
| 02 | Alta sin `blocked_reason` | 201 |
| 03 | Consulta de email en lista negra | 200, `blacklisted: true` |
| 04 | Consulta de email no listado | 200, `blacklisted: false` |
| 05 | Alta de email duplicado | 409 |
| 06 | `POST` sin token | 401 |
| 07 | `POST` con token inválido | 401 |
| 08 | `GET` sin token | 401 |
| 09 | Email con formato inválido | 400 |
| 10 | `app_uuid` faltante | 400 |
| 11 | `app_uuid` con formato inválido | 400 |
| 12 | `blocked_reason` de más de 255 caracteres | 400 |

> El environment se exporta con `bearer_token` vacío a propósito, para no versionar el
> secreto. Debe completarse al importarlo.

### Pruebas automatizadas

Adicionalmente, el repositorio incluye **25 pruebas automatizadas** del contrato del
API (`pytest`), que cubren autorización, validación de cada campo, duplicados,
normalización de emails, registro interno de IP y fecha/hora, e imposibilidad de
suplantar la IP del cliente.

> 📸 **[CAPTURA 16]** *(opcional)* — Salida de `pytest` con las 25 pruebas en verde.

---

## 7. Estrategias de despliegue

Se ejecutaron cuatro estrategias distintas sobre el entorno `blacklist-env`, todas
sobre un grupo de autoescalado de mínimo 3 y máximo 6 instancias.

### 7.1 Resultados comparados

| Estrategia | Tiempo total | Antes | Pico | Después | Conservadas | Nuevas | ¿Iniciales o nuevas? |
|---|---|---|---|---|---|---|---|
| All at once | **0 m 28 s** | 3 | 3 | 3 | 3 | 0 | Sobre las **iniciales** |
| Rolling (33 %) | **8 m 14 s** | 3 | 3 | 3 | 3 | 0 | Sobre las **iniciales** |
| Rolling with additional batch (33 %) | **9 m 27 s** | 3 | **4** | 3 | 3 | 1 | Mayoría iniciales, **1 nueva** |
| Immutable | **18 m 42 s** | 3 | **6** | 3 | 0 | **3** | **Todas nuevas** |

### 7.2 Cómo se validó que cada despliegue quedó en ejecución

Para las cuatro estrategias se aplicó la misma verificación, combinando el estado
reportado por AWS con pruebas funcionales reales contra la URL pública:

1. **Estado del entorno:** se esperó a que `Status` volviera a `Ready` y se registró
   `Health`, `HealthStatus` y `VersionLabel`, para confirmar que la versión
   efectivamente desplegada era la nueva y no la anterior.
2. **Health check HTTP:** `GET /` debía responder **200**.
3. **Escritura real en base de datos:** `POST /blacklists` con un email único debía
   responder **201**, lo que prueba que la aplicación no solo arrancó sino que conserva
   conectividad con el RDS.
4. **Lectura real:** `GET /blacklists/<email>` sobre ese email debía responder **200**
   con `blacklisted: true`.
5. **Registro de eventos:** se capturó el log de eventos para la ventana exacta del
   despliegue.

Las cuatro estrategias superaron los cuatro puntos.

### 7.3 All at once — 0 m 28 s

> 📸 **[CAPTURA 17]** — Eventos del despliegue con política *All at once*.

> 📸 **[CAPTURA 18]** — Pestaña *Estado y supervisión* durante el despliegue, donde se
> aprecia que las 3 instancias se actualizan simultáneamente.

- **Instancias utilizadas:** 3 (las mismas antes y después).
- **Sobre instancias iniciales o nuevas:** sobre las **iniciales**, 0 nuevas.
- **Hallazgos:** es con diferencia la más rápida, **unas 18 veces más rápida que
  Rolling**. Actualiza las tres instancias a la vez y no espera a que el balanceador
  vuelva a registrarlas como sanas antes de dar por terminado el despliegue. Ese es
  exactamente su costo: durante esos segundos **ninguna instancia sirve la versión
  estable**, de modo que hay una ventana de indisponibilidad. Aceptable en desarrollo,
  desaconsejable en producción.

### 7.4 Rolling — 8 m 14 s

> 📸 **[CAPTURA 19]** — Eventos mostrando los lotes (`Batch 1`, `Batch 2`, `Batch 3`).

- **Instancias utilizadas:** 3 (las mismas antes y después). Lotes del 33 %.
- **Sobre instancias iniciales o nuevas:** sobre las **iniciales**, 0 nuevas.
- **Hallazgos:** despliega en tres lotes de una instancia; en cada uno espera a que la
  instancia se registre de nuevo en el balanceador y quede sana. Eso explica la
  diferencia de tiempo frente a *All at once*. **No hay interrupción del servicio**,
  pero sí **capacidad reducida**: mientras un lote se actualiza solo quedan dos de tres
  instancias atendiendo. Con carga cercana al límite, esa pérdida de un tercio de la
  capacidad puede degradar los tiempos de respuesta.

### 7.5 Rolling with additional batch — 9 m 27 s

> 📸 **[CAPTURA 20]** — Eventos mostrando el lote adicional y el mensaje
> `Terminating excess instance(s)`.

> 📸 **[CAPTURA 21]** — Pestaña *Estado y supervisión* durante el despliegue, con **4
> instancias** simultáneas.

- **Instancias utilizadas:** 3 iniciales + **1 adicional** = 4 en el pico; vuelve a 3.
- **Sobre instancias iniciales o nuevas:** mayoría iniciales, **1 nueva**.
- **Hallazgos:** solo **1 m 13 s más lenta que Rolling**, y resuelve justamente su punto
  débil. Antes de empezar lanza un lote adicional y al terminar elimina la sobrante. El
  log lo muestra de forma explícita:

  ```
  Batch 3: Completed application deployment.
  Terminating excess instance(s): [i-00e270e388727945c].
  Excess instance(s) terminated.
  ```

  Gracias a ese lote extra **la capacidad nunca baja de las tres instancias
  originales**. Es el mejor equilibrio entre tiempo y disponibilidad: por poco más de un
  minuto se elimina la degradación de capacidad.

  Observación: al finalizar, el entorno quedó momentáneamente en estado `Degraded`
  mientras la instancia excedente terminaba de darse de baja, aunque el servicio
  respondió correctamente durante todo el proceso.

### 7.6 Immutable — 18 m 42 s

> 📸 **[CAPTURA 22]** — Eventos mostrando
> `Created temporary auto scaling group` y
> `Deployment succeeded. Terminating old instances and temporary Auto Scaling group`.

> 📸 **[CAPTURA 23]** — Pestaña *Estado y supervisión* durante el despliegue, con
> **6 instancias** simultáneas. Es la evidencia visual más clara de las cuatro.

- **Instancias utilizadas:** 3 iniciales + 3 nuevas = **6 en el pico**; termina con 3.
- **Sobre instancias iniciales o nuevas:** sobre instancias **completamente nuevas**;
  las 3 iniciales fueron reemplazadas.
- **Hallazgos:** la más lenta y la única que reemplaza el 100 % de las instancias. Crea
  un **grupo de autoescalado temporal paralelo**, levanta primero una instancia para
  verificar que la nueva versión arranca sana, y solo entonces completa el resto:

  ```
  Immutable deployment policy enabled. Launching one instance with the new settings to verify health.
  Created temporary auto scaling group awseb-e-tmjacz9vtk-immutable-stack-...
  Detached new instance(s) from temporary auto scaling group ...
  Deployment succeeded. Terminating old instances and temporary Auto Scaling group.
  ```

  El entorno llega a **6 instancias simultáneas**, que es precisamente el máximo
  configurado: **con un máximo menor que el doble del mínimo, esta estrategia no
  cabría**. Eso justifica la recomendación del enunciado de usar un grupo de 3 a 6.

  Es la más segura de las cuatro: si la nueva versión no arranca, las instancias viejas
  nunca se tocan y la reversión es inmediata. A cambio, consume el doble de instancias
  y el triple de tiempo.

### 7.7 Conclusión sobre las estrategias

No hay una estrategia mejor en abstracto; la elección depende de qué se quiera proteger:

- **Velocidad por encima de todo, sin importar la caída:** All at once.
- **Sin caída, aceptando capacidad reducida:** Rolling.
- **Sin caída y sin perder capacidad, por poco más de tiempo:** Rolling with additional
  batch. Para este servicio es la opción más equilibrada.
- **Máxima seguridad y reversión instantánea:** Immutable, asumiendo el doble de
  instancias y el triple de tiempo.

---

## 8. Hallazgo adicional: un `.ebextensions` puede romper los redespliegues

Durante las pruebas se encontró un fallo que merece registrarse, porque **su síntoma no
apunta a su causa**.

El archivo `.ebextensions/01_packages.config` instalaba los paquetes de sistema
`libpq-devel` y `gcc`. **La creación inicial del entorno funcionó sin problemas**, pero
todos los redespliegues posteriores fallaban con un mensaje genérico:

```
[Instance: i-xxxx] Command failed on instance. An unexpected error has occurred [ErrorCode: 0000000001].
Command execution completed on all instances. Summary: [Successful: 0, Failed: 2, TimedOut: 1].
Failed to deploy application.
```

Ese mensaje no indica qué falló. La causa solo se encontró leyendo `eb-engine.log` en la
instancia, donde el registro se corta exactamente en la fase que ejecuta los
`.ebextensions`:

```
[INFO] Executing instruction: PreBuildEbExtension
[INFO] Running command: /opt/aws/bin/cfn-init ... --configsets Infra-EmbeddedPreBuild
      (sin más salida; 21 segundos después, "Command failed")
```

Agrava el problema que las instancias quedan **bloqueadas en estado "Performing
application deployment"** indefinidamente y hay que reemplazarlas manualmente.

Esos paquetes nunca fueron necesarios: el proyecto usa `psycopg2-binary`, que se
distribuye como rueda precompilada y no requiere compilador ni cabeceras de PostgreSQL.
Se reemplazó el bloque `packages` por `option_settings`, y a partir de ahí los cuatro
despliegues se ejecutaron sin incidentes.

**Lección:** un `.ebextensions` que funciona al crear el entorno no está validado hasta
que se ha probado un **redespliegue** sobre instancias ya existentes.

---

## 9. Segundo hallazgo: la IP registrada detrás del balanceador

El enunciado exige guardar *"la dirección IP desde donde se hace la solicitud"*. La
primera versión registraba `172.31.35.99`, una **dirección privada de la VPC**, no la
del cliente.

La causa es que en Elastic Beanstalk la cadena de proxies es
`cliente → ALB → nginx → gunicorn`, y **cada proxy agrega un salto** a la cabecera
`X-Forwarded-For`. Confiando en un solo salto se obtenía la IP del balanceador.

La corrección consistió en confiar en **dos saltos** (`ProxyFix(x_for=2)`), lo que se
verificó en producción comparando la IP registrada con la IP pública real del cliente:

```
Mi IP real:    186.29.120.221
IP registrada: 186.29.120.221   ← correcto
```

Exigir dos saltos tiene además un efecto de seguridad: **un cliente no puede suplantar
su IP** enviando su propio `X-Forwarded-For`, porque no alcanza los saltos de confianza
requeridos. Ese comportamiento quedó cubierto con una prueba automatizada.

---

## 10. Conclusiones

> `[COMPLETAR]` Escriba aquí sus conclusiones. Algunas ideas, a partir de lo observado:
>
> - El despliegue manual sobre un PaaS elimina la gestión de servidores, pero no la de
>   la configuración: los fallos encontrados no estaban en el código de la aplicación
>   sino en la configuración de la plataforma.
> - La elección de la estrategia de despliegue es una decisión de negocio, no técnica:
>   se intercambia tiempo por disponibilidad.
> - La separación de credenciales en variables de entorno permitió mantener el
>   repositorio público sin exponer secretos.
> - `[COMPLETAR con sus propias observaciones]`

---

## Anexo: cómo reproducir el despliegue

1. Crear la instancia RDS PostgreSQL en la misma VPC y región del entorno.
2. Configurar el grupo de seguridad del RDS para aceptar el puerto 5432 únicamente
   desde el grupo de seguridad de las instancias de Beanstalk.
3. Crear la aplicación y el entorno en Elastic Beanstalk con plataforma Python.
4. Configurar las variables de entorno `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`,
   `DB_NAME` y `STATIC_BEARER_TOKEN`.
5. Desplegar el paquete de código fuente. La tabla `blacklist_entries` se crea
   automáticamente en el primer arranque.
