#!/bin/sh
# Inicialização no Render: aplica migrações e sobe o Gunicorn.
set -e

python manage.py migrate --noinput
python manage.py createcachetable

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 60 \
  --access-logfile - \
  --forwarded-allow-ips "*"
