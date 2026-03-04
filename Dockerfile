# ── Stage base ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Evitar archivos .pyc y habilitar salida sin buffer (logs en tiempo real)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Stage de dependencias ─────────────────────────────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage final ───────────────────────────────────────────────────────────────
FROM deps AS final

COPY . .

# Puerto por defecto (se sobreescribe en docker-compose)
EXPOSE 8000

# Comando por defecto: FastAPI con uvicorn
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
