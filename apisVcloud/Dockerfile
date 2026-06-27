FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ISEU_PROJECT_ROOT=/app \
    AWS_REGION=eu-west-1

WORKDIR /app

COPY apisVcloud/requirements.txt /app/apisVcloud/requirements.txt
RUN pip install --no-cache-dir -r /app/apisVcloud/requirements.txt

COPY ["api_clients/intento 3/APIS", "/app/api_clients/intento 3/APIS"]
COPY ["api_clients/intento 3/pipeline", "/app/api_clients/intento 3/pipeline"]
COPY ["api_clients/intento 3/run_pipeline.py", "/app/api_clients/intento 3/run_pipeline.py"]
COPY apisVcloud /app/apisVcloud

RUN mkdir -p "/app/api_clients/intento 3/data_lake/bronze" \
    "/app/api_clients/intento 3/data_lake/silver" \
    "/app/api_clients/intento 3/data_lake/gold" \
    "/app/api_clients/intento 3/reports"

ENTRYPOINT ["python", "-m", "apisVcloud.cloud_pipeline"]

