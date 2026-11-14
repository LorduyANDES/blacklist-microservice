# Imagen del microservicio de lista negra global, pensada para AWS Fargate.
#
# No necesita compilador: psycopg2-binary se distribuye como rueda precompilada,
# que fue justamente el hallazgo que rompia los redespliegues en la entrega 1.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Las dependencias se copian antes que el codigo a proposito: mientras
# requirements.txt no cambie, Docker reutiliza esta capa y la construccion en
# CodeBuild baja de minutos a segundos.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Solo el codigo que corre en produccion. Las pruebas, la documentacion y la
# coleccion de Postman se quedan fuera (ver .dockerignore).
COPY application.py config.py models.py auth.py views.py ./

# El proceso no corre como root. Si alguien lograra ejecutar codigo a traves de
# la aplicacion, no heredaria privilegios dentro del contenedor.
RUN useradd --create-home --uid 10001 microservicio \
    && chown -R microservicio:microservicio /app
USER microservicio

EXPOSE 8000

# Mismo comando que servia la aplicacion en Elastic Beanstalk, con los registros
# dirigidos a la salida estandar para que Fargate los entregue a CloudWatch.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "application:application"]
