FROM python:3.12-alpine3.24

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY orchestrator/pyproject.toml /app/
RUN pip install --upgrade pip && pip install "."

COPY orchestrator/app /app/app
COPY orchestrator/config /app/config

RUN addgroup -S orchestrator \
    && adduser -S -G orchestrator orchestrator \
    && mkdir -p /app/data \
    && chown -R orchestrator:orchestrator /app/data
USER orchestrator

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
