# Stage 1 — build the React app
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2 — serve with nginx + proxy to backend
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Place config in templates/ so nginx uses envsubst to inject BACKEND_URL at runtime
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
