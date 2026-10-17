# Estrategias de despliegue en AWS Elastic Beanstalk

Resultados de ejecutar cuatro estrategias de despliegue distintas sobre el entorno
`blacklist-env`, el 17 de octubre de 2026.

## Entorno utilizado

| Parámetro | Valor |
|---|---|
| Región | us-east-2 (Ohio) |
| Plataforma | Python 3.13 sobre 64bit Amazon Linux 2023 / 4.13.10 |
| Tipo de entorno | Con balanceador (Application Load Balancer) |
| Tipo de instancia | `t3.micro` |
| Grupo de autoescalado | Mínimo 3, máximo 6 |
| Health check | `GET /`, código esperado 200 |
| Base de datos | RDS PostgreSQL 16.15, `db.t3.micro`, sin acceso público |

Las cuatro estrategias requieren más de una instancia, como exige el enunciado.

## Resultados comparados

| Estrategia | Tiempo total | Instancias antes | Pico | Después | Conservadas | Nuevas | ¿Sobre instancias iniciales o nuevas? |
|---|---|---|---|---|---|---|---|
| All at once | **0 m 28 s** | 3 | 3 | 3 | 3 | 0 | Sobre las **iniciales** |
| Rolling (33 %) | **8 m 14 s** | 3 | 3 | 3 | 3 | 0 | Sobre las **iniciales** |
| Rolling with additional batch (33 %) | **9 m 27 s** | 3 | **4** | 3 | 3 | 1 | Mayoría iniciales, **1 nueva** |
| Immutable | **18 m 42 s** | 3 | **6** | 3 | 0 | **3** | Sobre instancias **completamente nuevas** |

## Cómo se validó que cada despliegue quedó en ejecución

Para cada estrategia se aplicó la misma verificación, combinando el estado reportado
por AWS con pruebas funcionales reales contra la URL pública del entorno:

1. **Estado del entorno:** se esperó a que `Status` volviera a `Ready` y se registró
   `Health`, `HealthStatus` y, sobre todo, `VersionLabel`, para confirmar que la
   versión efectivamente desplegada era la nueva y no la anterior.
2. **Health check HTTP:** `GET /` debía responder **200**.
3. **Escritura real en base de datos:** `POST /blacklists` con un email único por
   ejecución debía responder **201**, lo que prueba que la aplicación no solo
   arrancó sino que conserva conectividad con el RDS.
4. **Lectura real:** `GET /blacklists/<email>` sobre ese mismo email debía responder
   **200** con `blacklisted: true`.
5. **Registro de eventos:** se capturó el log de eventos de la consola para la
   ventana exacta del despliegue.

Las cuatro estrategias superaron los cuatro puntos.

## Hallazgos por estrategia

### All at once — 0 m 28 s

Con diferencia la más rápida: **unas 18 veces más rápida que Rolling**. Actualiza las
tres instancias a la vez y no espera a que el balanceador vuelva a registrarlas como
sanas antes de dar por terminado el despliegue.

Ese es exactamente su costo. Durante esos segundos **ninguna instancia está sirviendo
la versión estable**, de modo que hay una ventana de indisponibilidad. Es aceptable en
un entorno de desarrollo y desaconsejable en producción.

Reutiliza las instancias existentes: no se creó ninguna instancia nueva.

### Rolling (lotes del 33 %) — 8 m 14 s

Despliega en tres lotes de una instancia. En cada lote espera a que la instancia se
registre de nuevo en el balanceador y quede sana antes de pasar al siguiente, lo que
explica la diferencia de tiempo frente a *All at once*.

**No hay interrupción del servicio**, pero sí **capacidad reducida**: mientras un lote
se actualiza, solo quedan dos de tres instancias atendiendo tráfico. Con una carga
cercana al límite, esa pérdida de un tercio de la capacidad puede degradar los tiempos
de respuesta.

Reutiliza las instancias existentes.

### Rolling with additional batch (lotes del 33 %) — 9 m 27 s

Solo **1 m 13 s más lenta que Rolling**, y resuelve justamente su punto débil. Antes
de empezar lanza un lote adicional, de modo que el entorno llega a **4 instancias**, y
al terminar elimina la sobrante. El log de eventos lo muestra de forma explícita:

```
Batch 3: Completed application deployment.
Terminating excess instance(s): [i-00e270e388727945c].
Excess instance(s) terminated.
```

Gracias a ese lote extra **la capacidad nunca baja de las tres instancias originales**.
Es el mejor equilibrio entre tiempo y disponibilidad de las cuatro: por poco más de un
minuto adicional se elimina la degradación de capacidad.

Observación: al finalizar, el entorno quedó momentáneamente en estado `Degraded`
mientras la instancia excedente terminaba de darse de baja, aunque el servicio
respondía correctamente (200 y 201) durante todo el proceso.

### Immutable — 18 m 42 s

La más lenta, y la única que **reemplaza el 100 % de las instancias**. Los eventos
muestran el mecanismo con claridad:

```
Immutable deployment policy enabled. Launching one instance with the new settings to verify health.
Created temporary auto scaling group awseb-e-tmjacz9vtk-immutable-stack-...
Detached new instance(s) from temporary auto scaling group ...
Deployment succeeded. Terminating old instances and temporary Auto Scaling group.
```

Crea un **grupo de autoescalado temporal paralelo**, levanta primero una instancia para
verificar que la nueva versión arranca sana, y solo entonces completa el resto. El
entorno llega a **6 instancias simultáneas** (3 antiguas + 3 nuevas), que es
precisamente el máximo configurado: **con un máximo menor que el doble del mínimo, esta
estrategia no cabría**.

Es la más segura de las cuatro. Si la nueva versión no arranca, las instancias viejas
nunca se tocan y la reversión es inmediata. A cambio, es la que más tiempo y más
recursos consume.

## Conclusión

No hay una estrategia mejor en abstracto; la elección depende de qué se quiera
proteger:

- **Velocidad por encima de todo, sin importar la caída:** All at once.
- **Sin caída, aceptando capacidad reducida:** Rolling.
- **Sin caída y sin perder capacidad, por poco más de tiempo:** Rolling with additional
  batch. Para este servicio es la opción más equilibrada.
- **Máxima seguridad y reversión instantánea:** Immutable, asumiendo el doble de
  instancias y el triple de tiempo.

## Hallazgo adicional: un `.ebextensions` puede romper los redespliegues

Durante estas pruebas se encontró un fallo que merece registrarse, porque su síntoma no
apunta a su causa.

El archivo `.ebextensions/01_packages.config` instalaba los paquetes de sistema
`libpq-devel` y `gcc`. **La creación inicial del entorno funcionó sin problemas**, pero
todos los redespliegues posteriores fallaban con un mensaje genérico:

```
[Instance: i-xxxx] Command failed on instance. An unexpected error has occurred [ErrorCode: 0000000001].
Command execution completed on all instances. Summary: [Successful: 0, Failed: 2, TimedOut: 1].
Failed to deploy application.
```

Ese mensaje no indica qué falló. La causa solo se encontró leyendo `eb-engine.log` en
la instancia, donde el registro se corta exactamente en la fase que ejecuta los
`.ebextensions`:

```
[INFO] Executing instruction: PreBuildEbExtension
[INFO] Running command: /opt/aws/bin/cfn-init ... --configsets Infra-EmbeddedPreBuild
      (sin más salida; 21 segundos después, "Command failed")
```

Agrava el problema que las instancias quedan **bloqueadas en estado "Performing
application deployment"** indefinidamente y hay que reemplazarlas a mano.

Esos paquetes nunca fueron necesarios: el proyecto usa `psycopg2-binary`, que se
distribuye como rueda precompilada y no requiere compilador ni cabeceras de PostgreSQL.
Se reemplazó el bloque `packages` por `option_settings`, y a partir de ahí los cuatro
despliegues se ejecutaron sin incidentes.

**Lección:** un `.ebextensions` que funciona al crear el entorno no está validado hasta
que se ha probado un redespliegue sobre instancias ya existentes.
