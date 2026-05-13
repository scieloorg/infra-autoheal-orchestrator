FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml /app/
RUN pip install --upgrade pip && pip install ".[dev]"

COPY app /app/app
COPY config /app/config

RUN adduser --disabled-password --gecos "" orchestrator
USER orchestrator

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
