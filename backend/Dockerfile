FROM cgr.dev/chainguard/python:latest-dev AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM cgr.dev/chainguard/python:latest

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /app/venv /app/venv
COPY backend/__init__.py ./backend/__init__.py
COPY backend/app ./backend/app
COPY frontend ./frontend

EXPOSE 8000

ENTRYPOINT ["python"]
CMD ["-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
