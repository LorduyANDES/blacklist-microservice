# Proyecto 1 — Entrega 3
## Entrega continua sobre AWS Fargate con CodeDeploy y CodePipeline

**Programa:** Maestría en Inteligencia Artificial (MAIA)

**Universidad de los Andes**

**Autor:** Jesús Daniel Lorduy — j.lorduy@uniandes.edu.co

**Fecha:** 15 de noviembre de 2026

---

## Enlaces de la entrega

| Recurso | Enlace |
|---|---|
| Repositorio GitHub | https://github.com/LorduyANDES/blacklist-microservice |
| Aplicación sobre Fargate | http://blacklist-alb-1630846931.us-east-2.elb.amazonaws.com |
| Documentación publicada de Postman | https://documenter.getpostman.com/view/59043927/2sBYHSy11e |
| Video de sustentación | https://www.youtube.com/watch?v=4CyqHhOnwIQ |

> La URL cambió respecto a las entregas anteriores: el microservicio ya no corre sobre
> Elastic Beanstalk sino sobre contenedores en Fargate, detrás de un balanceador nuevo.
> El entorno de Beanstalk se desmontó una vez calificada la entrega 2.

---

## 1. Alcance de esta entrega

Esta entrega cambia dos cosas respecto a la anterior.

La primera es **dónde corre el microservicio**: deja de ser una aplicación desplegada
sobre instancias gestionadas por Elastic Beanstalk y pasa a ser **un contenedor sobre
AWS Fargate**, sin servidores que administrar.

La segunda es **hasta dónde llega el pipeline**. En la entrega 2 construía un artefacto
y se detenía ahí deliberadamente, porque el enunciado prohibía el despliegue
automatizado. Ahora el pipeline **despliega solo**: cada commit en la rama principal
ejecuta las pruebas, construye la imagen del contenedor, la publica en Amazon ECR y
CodeDeploy la pone en producción mediante un despliegue azul/verde.

Lo que no cambia es el microservicio en sí: el mismo código, los mismos tres endpoints
y las mismas 25 pruebas unitarias de la entrega 2.

---

## 2. Arquitectura

```
   Commit en main
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ CodePipeline  blacklist-microservice-ci                      │
│                                                              │
│  1. Fuente         GitHub, por conexion de CodeConnections   │
│                                                              │
│  2. Construccion   AWS CodeBuild                             │
│       pre_build    pruebas unitarias  ◄── corta aqui si fallan│
│       build        imagen Docker  →  Amazon ECR              │
│       post_build   imageDetail.json                          │
│       artefactos   taskdef.json, appspec.yaml                │
│                                                              │
│  3. Despliegue     AWS CodeDeploy, azul/verde                │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
        ┌──────────────────────────────────────┐
        │  Balanceador  blacklist-alb          │
        │    grupo azul  ◄── trafico           │
        │    grupo verde ◄── version nueva     │
        └──────────────┬───────────────────────┘
                       ▼
              Servicio ECS sobre Fargate
                       │
                       ▼
              RDS PostgreSQL (reutilizado)
```

Recursos creados para esta entrega, todos en **us-east-2**:

| Recurso | Nombre |
|---|---|
| Repositorio de imágenes | ECR `blacklist-microservice` |
| Clúster y servicio | ECS `blacklist-cluster` / `blacklist-service` |
| Definición de tarea | `blacklist-task`, contenedor `blacklist`, puerto 8000 |
| Balanceador | `blacklist-alb` |
| Grupos de destino | `blacklist-tg-azul` y `blacklist-tg-verde` |
| Grupos de seguridad | `blacklist-alb-sg`, `blacklist-fargate-sg` |
| Roles | `blacklist-ecs-execution-role`, `blacklist-ecs-task-role`, `blacklist-codedeploy-role` |
| Aplicación de despliegue | CodeDeploy `blacklist-app` / grupo `blacklist-dg` |
| Alarmas | `blacklist-destinos-no-sanos-azul` y `-verde` |

El RDS PostgreSQL de las entregas anteriores **se conserva y se reutiliza**: cambió la
plataforma de cómputo, no la persistencia.

---

## 3. Configuración de la plataforma de contenedores (20 %)

### 3.1 El contenedor

El `Dockerfile` parte de `python:3.13-slim` y sirve la aplicación con el mismo comando
de Gunicorn que usaba Elastic Beanstalk.

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Las dependencias antes que el codigo: mientras requirements.txt no cambie,
# Docker reutiliza esta capa y la construccion baja de minutos a segundos.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY application.py config.py models.py auth.py views.py ./

# El proceso no corre como root.
RUN useradd --create-home --uid 10001 microservicio \
    && chown -R microservicio:microservicio /app
USER microservicio

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2",
     "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-",
     "application:application"]
```

Tres decisiones que conviene justificar:

- **No hace falta compilador.** `psycopg2-binary` se distribuye como rueda
  precompilada. Ese fue exactamente el hallazgo que rompía los redespliegues en la
  entrega 1, cuando un `.ebextensions` instalaba `gcc` y `libpq-devel` sin necesidad.
- **El proceso no corre como root.** Si alguien lograra ejecutar código a través de la
  aplicación, no heredaría privilegios dentro del contenedor.
- **Los registros van a la salida estándar.** Es lo que permite que Fargate los
  entregue a CloudWatch sin configuración adicional.

Un `.dockerignore` deja fuera de la imagen las pruebas, la documentación, la colección
de Postman y, sobre todo, cualquier archivo `.env`.

### 3.2 Red y acceso a la base de datos

Las tareas corren en las **subredes públicas** de la VPC con IP pública asignada. Es una
decisión deliberada: una tarea en subred privada necesitaría un NAT Gateway para
descargar su imagen de ECR, y ese recurso costaría más que todo el resto del montaje
junto. La exposición se controla con grupos de seguridad, no con topología:

| Grupo | Entrada permitida |
|---|---|
| `blacklist-alb-sg` | puerto 80 desde cualquier origen |
| `blacklist-fargate-sg` | puerto 8000 **solo desde el grupo del balanceador** |
| `blacklist-rds-sg` | puerto 5432 **solo desde el grupo de las tareas** |

Nadie puede alcanzar el contenedor directamente, ni la base de datos desde internet.

### 3.3 Los secretos no viajan en el repositorio

Esta es la decisión de diseño más importante del montaje.

CodeDeploy necesita un archivo `taskdef.json` **en el repositorio**, y ese repositorio
es **público**. Si la contraseña del RDS o el token Bearer estuvieran escritos ahí,
estarían publicados en GitHub.

La solución aprovecha que `config.py` ya admitía una variable `DATABASE_URL` que
reemplaza a las demás: toda la configuración de base de datos viaja en **un único
parámetro cifrado** de AWS Systems Manager Parameter Store.

| Parámetro | Tipo | Contenido |
|---|---|---|
| `/blacklist/database_url` | SecureString | Usuario, contraseña, endpoint y base |
| `/blacklist/static_bearer_token` | SecureString | Token Bearer de los endpoints |

La definición de tarea los referencia por ARN, nunca por valor. El rol de ejecución
tiene permiso para leer **solo** los parámetros bajo `/blacklist/` y para descifrarlos
únicamente a través de SSM.

> **Figura 1** — El contenedor en la consola: las dos variables aparecen como
> `valueFrom` apuntando a Parameter Store. No hay un solo secreto en claro.

### 3.4 El servicio sobre Fargate

El servicio se creó con el controlador de despliegue puesto en **CodeDeploy** desde el
principio, que es lo que habilita el azul/verde. La tarea usa 0,25 vCPU y 512 MB, el
tamaño más pequeño de Fargate, suficiente para este microservicio.

El despliegue manual inicial se validó contra la URL del balanceador:

```
GET  /                                  → 200
GET  /blacklists/<email>  sin token     → 401
POST /blacklists          con token     → 201
GET  /blacklists/<email>  con token     → 200  {"blacklisted": true}
```

El **201** y el **true** son la prueba de fondo: significan que el contenedor leyó los
parámetros cifrados, se conectó al RDS y escribió en él.

> **Figura 2** — El servicio en ejecución: estado activo, una tarea corriendo, un
> destino sano detrás del balanceador.

---

## 4. Archivos de configuración para CodeDeploy (10 %)

Son dos, y viven en la raíz del repositorio.

**`taskdef.json`** describe la tarea. El marcador `<IMAGE1_NAME>` lo sustituye
CodePipeline por la imagen recién construida:

```json
{
  "family": "blacklist-task",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [{
    "name": "blacklist",
    "image": "<IMAGE1_NAME>",
    "portMappings": [{ "containerPort": 8000, "protocol": "tcp" }],
    "secrets": [
      { "name": "DATABASE_URL",
        "valueFrom": "arn:aws:ssm:...:parameter/blacklist/database_url" },
      { "name": "STATIC_BEARER_TOKEN",
        "valueFrom": "arn:aws:ssm:...:parameter/blacklist/static_bearer_token" }
    ]
  }]
}
```

**`appspec.yaml`** le dice a CodeDeploy qué servicio actualizar y por dónde entra el
tráfico. El marcador `<TASK_DEFINITION>` lo sustituye la revisión que CodePipeline
acaba de registrar:

```yaml
version: 0.0
Resources:
  - TargetService:
      Type: AWS::ECS::Service
      Properties:
        TaskDefinition: <TASK_DEFINITION>
        LoadBalancerInfo:
          ContainerName: "blacklist"
          ContainerPort: 8000
        PlatformVersion: "LATEST"
```

El nombre del contenedor y el puerto **deben coincidir** entre los dos archivos y con lo
que el proceso realmente escucha. La sección 8.3 muestra qué pasa cuando no coinciden.

Las **pruebas unitarias se ejecutan durante la construcción**, antes de cualquier otra
cosa, como se detalla en la sección siguiente.

---

## 5. La construcción crea la imagen del contenedor (10 %)

El `buildspec.yml` conserva el diseño de la entrega 2 —las pruebas en `pre_build`, como
puerta del proceso— y añade la construcción y publicación de la imagen:

```yaml
  pre_build:
    commands:
      - pip install -r requirements-dev.txt
      # Puerta del proceso: una fase que falla aborta las siguientes.
      - python -m pytest -v --junitxml=reports/pruebas-unitarias.xml
      # La cuenta se deduce en tiempo de construccion, no se escribe en el repositorio.
      - CUENTA=$(aws sts get-caller-identity --query Account --output text)
      - REGISTRO=$CUENTA.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
      - aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRO
      - ETIQUETA=${CODEBUILD_RESOLVED_SOURCE_VERSION:0:7}

  build:
    commands:
      - docker build -t $REGISTRO/$ECR_REPO:$ETIQUETA -t $REGISTRO/$ECR_REPO:latest .
      - docker push $REGISTRO/$ECR_REPO:$ETIQUETA
      - docker push $REGISTRO/$ECR_REPO:latest

  post_build:
    commands:
      - printf '{"ImageURI":"%s"}' "$REGISTRO/$ECR_REPO:$ETIQUETA" > imageDetail.json

artifacts:
  files:
    - imageDetail.json
    - taskdef.json
    - appspec.yaml
```

**Cada imagen se etiqueta con el commit que la originó.** Dada una tarea en ejecución,
se puede saber exactamente de qué código salió, sin ambigüedad.

Para que CodeBuild pueda construir imágenes hizo falta habilitar el **modo
privilegiado** del proyecto y ampliar su rol con permisos de ECR, acotados al único
repositorio de este proyecto.

> **Figura 3** — El repositorio de ECR. Cada imagen lleva la etiqueta de su commit.

---

## 6. Despliegue continuo automático sobre Fargate (40 %)

### 6.1 La etapa del pipeline

El pipeline pasó de dos etapas a tres. La nueva usa la acción `CodeDeployToECS`, que
toma los tres archivos que produce la construcción:

```json
{
  "ApplicationName": "blacklist-app",
  "DeploymentGroupName": "blacklist-dg",
  "TaskDefinitionTemplateArtifact": "ArtefactoDesplegable",
  "TaskDefinitionTemplatePath": "taskdef.json",
  "AppSpecTemplateArtifact": "ArtefactoDesplegable",
  "AppSpecTemplatePath": "appspec.yaml",
  "Image1ArtifactName": "ArtefactoDesplegable",
  "Image1ContainerName": "IMAGE1_NAME"
}
```

> **Figura 4** — El pipeline con sus tres etapas. La de despliegue aparece como
> *Amazon ECS (Blue/Green)*.

### 6.2 Cómo funciona el azul/verde

El grupo de despliegue conoce el servicio de ECS, el balanceador y **dos grupos de
destino**. En todo momento uno sirve el tráfico y el otro está libre.

Cuando llega una versión nueva, CodeDeploy:

1. Levanta las tareas nuevas en el grupo libre, sin tocar las que están sirviendo
2. Espera a que el balanceador las declare sanas
3. Conmuta el escucha del balanceador hacia el grupo nuevo
4. Espera un minuto y termina las tareas antiguas

Si algo falla antes del paso 3, el tráfico nunca llega a moverse y las tareas viejas
siguen atendiendo. Esa es toda la gracia del método.

> **Figura 5** — El grupo de despliegue: tipo azul/verde, restauración habilitada, los
> dos grupos de destino y las dos alarmas conectadas.

### 6.3 La reversión automática

El grupo tiene activada la reversión ante dos eventos: fallo del despliegue y
**activación de alarma**. Las alarmas vigilan el número de destinos no sanos de cada
grupo, y saltan si hay al menos uno durante dos minutos seguidos.

Ese margen de dos minutos es deliberado: durante un despliegue normal las tareas nuevas
tardan unos segundos en pasar sus comprobaciones, y una alarma más nerviosa revertiría
despliegues sanos.

La sección 9 explica por qué estas alarmas no estaban ahí desde el principio y qué pasó
por no tenerlas.

---

## 7. Los tres escenarios (20 %)

Los tres se ejecutaron sobre el pipeline real, disparados por commits reales a la rama
principal.

> **Figura 6** — El historial de ejecuciones. Todas se disparan por commit; dos
> aparecen en **Error**, una por el escenario 7.1 y otra por el 7.3.

### 7.1 Pipeline de integración continua fallido (4 %)

**Qué se hizo.** Se endureció el límite del campo `blocked_reason` de 255 a 200
caracteres, sin revisar el contrato del API. Es el tipo de cambio que parece inocuo y
rompe un consumidor.

**Qué pasó.** La construcción murió en `pre_build`:

```
tests/test_blacklists.py::test_blocked_reason_de_exactamente_255_caracteres_es_valido FAILED

=================================== FAILURES ===================================
>       assert response.status_code == 201
E       assert 400 == 201

========================= 1 failed, 24 passed in 0.48s =========================

[Container] Phase complete: PRE_BUILD State: FAILED
```

**Hallazgos.** La etapa de despliegue **no llegó a ejecutarse**: el pipeline se detuvo
en la construcción. No se publicó imagen en ECR, no se registró definición de tarea y
CodeDeploy no creó ningún despliegue. El servicio siguió sirviendo la versión anterior
sin enterarse.

Esto confirma el diseño del `buildspec`: poner las pruebas en `pre_build` convierte todo
lo demás —imagen incluida— en una consecuencia de que las pruebas pasen.

> **Figura 7** — La construcción en estado *Error*, iniciada por el pipeline.
> **Figura 8** — El log: la prueba fallida, el detalle de la aserción y la fase
> `PRE_BUILD` terminando en `FAILED`.

### 7.2 Integración continua y entrega continua exitosas (8 %)

**Qué se hizo.** Se revirtió el cambio anterior, restaurando el límite de 255
caracteres.

**Qué pasó.** El pipeline recorrió las tres etapas. Las 25 pruebas pasaron, la imagen se
publicó en ECR etiquetada con el commit, y CodeDeploy completó los cuatro pasos del
despliegue azul/verde.

**Hallazgos.** El desvío de tráfico quedó en **0 % al conjunto original y 100 % al de
sustitución**, y todos los eventos del ciclo de vida se completaron correctamente. El
grupo de destino activo pasó de verde a azul: la conmutación ocurrió de verdad, no es
una etiqueta de éxito sobre el mismo conjunto de tareas.

El despliegue completo, desde el commit hasta el tráfico conmutado, tardó algo menos de
cinco minutos.

> **Figura 9** — El despliegue exitoso: cuatro pasos completados y el tráfico
> íntegramente en el conjunto de sustitución.

### 7.3 Integración continua exitosa y entrega continua fallida (8 %)

**Qué se hizo.** Se declaró el contenedor en el puerto **8080** en `taskdef.json` y
`appspec.yaml`, dejando a Gunicorn escuchando en el **8000**. Es un fallo realista: un
desajuste entre la configuración del despliegue y lo que la aplicación hace de verdad.

**Por qué el CI no puede detectarlo.** Las pruebas unitarias ejercitan la aplicación
Flask directamente; no leen la definición de tarea ni levantan el contenedor. El cambio
pasa las 25 pruebas sin inmutarse, y la imagen se construye y se publica con
normalidad. De hecho, la imagen de ese commit **existe en ECR** (figura 3): lo que
falló no fue construirla.

**Qué pasó.** El pipeline llegó a la etapa de despliegue y falló ahí:

```
Estado: Detenido
code: ALARM_ACTIVE
message: One or more alarms have been activated according to the Amazon CloudWatch
         metrics you selected, and the affected deployments have been stopped.
         Activated alarms: <blacklist-destinos-no-sanos-verde>
```

**Hallazgos.** Los cuatro pasos del despliegue figuran como **omitidos** y el desvío de
tráfico quedó en **100 % al conjunto original y 0 % al de sustitución**. Es decir: el
tráfico **nunca se movió**. El servicio siguió respondiendo 200 durante todo el
episodio, sirviendo la versión anterior.

Un despliegue fallido que no se nota desde fuera es exactamente lo que se le pide a una
entrega continua bien montada.

> **Figura 10** — El despliegue detenido por alarma, con todos los pasos omitidos y el
> tráfico intacto en el conjunto original.

---

## 8. Hallazgo principal: una reversión automática sin alarma no revierte nada

El escenario 7.3 se intentó **dos veces**, y la primera salió mal de una forma que vale
la pena documentar, porque el síntoma contradice lo que la consola decía.

### 8.1 Qué ocurrió

En el primer intento, el grupo de despliegue estaba configurado así:

```json
"alarmConfiguration": null,
"autoRollbackConfiguration": {
    "enabled": true,
    "events": ["DEPLOYMENT_FAILURE", "DEPLOYMENT_STOP_ON_ALARM"]
}
```

Con exactamente el mismo cambio roto, **CodeDeploy reportó el despliegue como
exitoso**, conmutó el tráfico al grupo verde y terminó las tareas antiguas. Las tareas
nuevas estaban *corriendo* —el contenedor arrancaba sin problema, Gunicorn escuchaba en
el 8000— pero el balanceador las comprobaba en el 8080 y nunca las declaró sanas.

El servicio quedó devolviendo **504 Gateway Timeout**.

### 8.2 Cuánto duró

La métrica del balanceador lo delimita con precisión: el grupo verde estuvo con **cero
destinos sanos entre las 13:06 y las 13:16**, hora local. **Once minutos** sin un solo
destino capaz de atender.

| Minuto (UTC−5) | Destinos sanos | Destinos no sanos |
|---|---|---|
| 12:55 – 12:59 | 1 | 0 |
| **13:06 – 13:16** | **0** | **1** (pico de 2) |
| 13:28 en adelante | 1 | 0 |

> **Figura 11** — La métrica del grupo verde durante el incidente: la línea de destinos
> sanos cae a cero y vuelve solo tras la corrección manual.

El servicio se restableció revirtiendo el cambio y dejando que el pipeline desplegara la
configuración correcta.

### 8.3 La causa

**La reversión por alarma estaba declarada, pero no había ninguna alarma conectada.** El
evento `DEPLOYMENT_STOP_ON_ALARM` figuraba en la configuración y `alarmConfiguration`
estaba en `null`: no existía nada capaz de dispararlo.

A eso se sumó que el grupo estaba configurado para conmutar el tráfico sin esperar
aprobación. CodeDeploy no tenía ningún motivo para detenerse: desde su punto de vista
las tareas estaban corriendo y el despliegue había terminado.

### 8.4 La lección

**Un despliegue azul/verde sin alarmas conectadas no protege de nada.** Es peor que no
tener reversión automática, porque la consola muestra `enabled: true` y transmite una
seguridad que no existe.

La corrección fue crear dos alarmas sobre `UnHealthyHostCount`, una por grupo de
destino, y conectarlas al grupo de despliegue. Con ellas, el mismo cambio roto produjo
el resultado del escenario 7.3: despliegue detenido, tráfico intacto, cero segundos de
indisponibilidad.

El mismo defecto, dos veces, con y sin red de seguridad. La diferencia entre once
minutos de caída y ninguno no estuvo en el código, sino en una línea de configuración.

---

## 9. Otros hallazgos

**La comprobación de salud del balanceador es la única que opina.** ECS considera que
una tarea está bien si el contenedor arranca y no se cae. Que el proceso escuche donde
debe, responda lo que debe y pueda hablar con su base de datos solo lo sabe el
balanceador. Un despliegue que no gate sobre esa señal está gateando sobre casi nada.

**Etiquetar la imagen con el commit paga enseguida.** Durante el diagnóstico del
incidente, poder mirar la definición de tarea en ejecución y leer `:0758fba` eliminó de
un vistazo la duda de qué código estaba sirviendo.

**Las subredes públicas con grupos de seguridad estrictos son una alternativa legítima
al NAT Gateway.** En este montaje nadie alcanza el contenedor salvo el balanceador, ni
la base de datos salvo las tareas, y el coste del NAT se evita por completo.

---

## 10. Estado de la aplicación

El microservicio corre sobre Fargate y es accesible vía Postman en la URL del
balanceador. Verificación al cierre:

```
GET  /                    → 200
POST /blacklists          → 201
GET  /blacklists/<email>  → 200   {"blacklisted": true}
```

La colección de Postman de las entregas anteriores sigue siendo válida; basta apuntar
`base_url` a la URL del balanceador.

---

## 11. Conclusiones

1. **El pipeline completa el ciclo.** De commit a producción sin intervención humana, en
   menos de cinco minutos, con las pruebas como puerta y el azul/verde como red.

2. **La entrega continua no es solo automatizar el despliegue, es automatizar la
   decisión de no desplegar.** Los dos escenarios fallidos de este documento valen más
   que el exitoso: uno impidió construir código roto, el otro impidió publicarlo.

3. **Un mecanismo de seguridad mal conectado es peor que su ausencia.** La reversión
   automática sin alarma mostraba `enabled: true` mientras dejaba pasar un despliegue
   que tumbó el servicio once minutos.

4. **El repositorio público obligó a un diseño mejor.** No poder escribir secretos en
   `taskdef.json` llevó a Parameter Store cifrado, que es como debería hacerse de todos
   modos.

5. **La contenerización simplificó lo que la entrega 1 complicaba.** El hallazgo del
   `.ebextensions` que rompía los redespliegues simplemente deja de existir: la imagen
   o se construye o no, y si se construye es idéntica en todas partes.

---

## 12. Declaración de uso de inteligencia artificial

Este proyecto se desarrolló con asistencia de un modelo de lenguaje (Claude, de
Anthropic), empleado como herramienta de apoyo en la escritura de código, la
configuración de los servicios de AWS, el diagnóstico de fallos y la redacción de este
documento. Los commits del repositorio registran esa coautoría mediante la línea
`Co-Authored-By`.

Todas las decisiones de arquitectura y la validación de los resultados fueron revisadas
por el autor. Las cifras, los estados y los registros reproducidos provienen de
ejecuciones reales sobre la cuenta de AWS del proyecto y no fueron estimados. El
incidente descrito en la sección 8 ocurrió de verdad y se documenta tal como sucedió.

---

## Anexo: cómo reproducir el montaje

1. **Imagen.** `Dockerfile` y `.dockerignore` en la raíz; repositorio en ECR.

2. **Secretos.** Dos parámetros SecureString en Parameter Store bajo `/blacklist/`. El
   rol de ejecución de la tarea necesita `ssm:GetParameters` sobre esa ruta y
   `kms:Decrypt` condicionado a `ssm`.

3. **Red.** Tres grupos de seguridad encadenados: balanceador ← tareas ← base de datos.
   Tareas en subredes públicas con IP pública, para no necesitar NAT Gateway.

4. **Balanceador.** Uno de aplicación con **dos** grupos de destino de tipo `ip` en el
   puerto 8000 y un escucha en el 80 apuntando al primero.

5. **ECS.** Clúster, definición de tarea y servicio con
   `deploymentController: CODE_DEPLOY` **desde su creación**: un servicio creado con el
   controlador por omisión no se puede convertir después.

6. **CodeDeploy.** Aplicación de plataforma ECS y grupo de despliegue azul/verde con los
   dos grupos de destino, el escucha de producción y **las alarmas conectadas**. Sin
   ellas la reversión automática no funciona, como demuestra la sección 8.

7. **Pipeline.** Tercera etapa con la acción `CodeDeployToECS`. El rol del pipeline
   necesita permisos de CodeDeploy, `ecs:RegisterTaskDefinition` y `iam:PassRole` sobre
   los roles de la tarea.

8. **Verificación.** Un commit en la rama principal debe producir, sin intervención, una
   imagen nueva en ECR, una revisión nueva de la definición de tarea y un despliegue con
   el tráfico conmutado al otro grupo de destino.
