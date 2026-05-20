FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY data ./data

EXPOSE 8000

# Production note: behind a reverse proxy you'd run multiple workers
# (e.g. uvicorn --workers 4), but each worker has its own in-memory store —
# the InMemoryRepository is single-process only. See README "Storage" section.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
