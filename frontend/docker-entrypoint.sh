#!/bin/sh
set -e

NGINX_PORT=${PORT:-80}
NGINX_BACKEND_URL=${BACKEND_URL:-http://localhost:8001}

echo "Starting nginx on port ${NGINX_PORT}, proxying to ${NGINX_BACKEND_URL}"

# Use sed with plain placeholders — no dollar signs, so nginx vars ($uri etc.) are never touched
sed \
  -e "s|NGINX_PORT|${NGINX_PORT}|g" \
  -e "s|NGINX_BACKEND_URL|${NGINX_BACKEND_URL}|g" \
  /etc/nginx/conf.d/default.conf.template \
  > /etc/nginx/conf.d/default.conf

nginx -t && exec nginx -g 'daemon off;'
