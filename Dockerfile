FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY data ./data

# Default to SQLite. /db is a dedicated mount point — bind-mount the project
# root there (`-v "$(pwd):/db"`) to have events.db appear in your repo root.
# Without a mount the DB lives in the container's writable layer and dies
# with the container; durable across restarts only when a volume is attached.
ENV TORCH_EVENTS_DB=/db/events.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
