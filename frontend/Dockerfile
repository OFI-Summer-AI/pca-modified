# Stage 1 — build the React app
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2 — serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy as a plain template — NOT into /etc/nginx/templates/ (that runs envsubst on ALL vars)
COPY nginx.conf /etc/nginx/conf.d/default.conf.template

EXPOSE 80

# Only substitute ${BACKEND_URL} and ${PORT} — nginx's own $uri, $proxy_host etc. are left untouched
CMD ["/bin/sh", "-c", "export PORT=${PORT:-80} && envsubst '${BACKEND_URL} ${PORT}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
