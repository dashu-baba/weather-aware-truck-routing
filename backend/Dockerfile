# syntax=docker/dockerfile:1
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --system --uid 10001 --home-dir /app app \
 && mkdir -p /data && chown app:app /data
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "1", "--threads", "4", "--timeout", "60", \
     "--access-logfile", "-", "--error-logfile", "-"]
