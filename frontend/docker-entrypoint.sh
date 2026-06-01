#!/bin/sh
set -e

# Set defaults so nginx config is always valid
export PORT=${PORT:-80}
export BACKEND_URL=${BACKEND_URL:-http://localhost:8001}

# Substitute ONLY ${PORT} and ${BACKEND_URL} — nginx's own $uri, $proxy_host etc. are untouched
envsubst '${PORT} ${BACKEND_URL}' \
  < /etc/nginx/conf.d/default.conf.template \
  > /etc/nginx/conf.d/default.conf

echo "nginx config written — BACKEND_URL=${BACKEND_URL} PORT=${PORT}"
exec nginx -g 'daemon off;'
