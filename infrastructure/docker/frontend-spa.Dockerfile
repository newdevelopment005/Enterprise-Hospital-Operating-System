# Build the EHOS SPA images. Usage:
#   docker build -f infrastructure/docker/frontend-spa.Dockerfile \
#     --build-arg APP=ehr-portal -t ehos/frontend-ehr-portal:latest .
FROM node:20-alpine AS build
ARG APP
WORKDIR /app
COPY frontend/apps/$APP/package*.json ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/apps/$APP/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA history fallback + /api proxy hints (override at ingress rather than bake).
RUN printf 'server { listen 80; root /usr/share/nginx/html; index index.html; location = /healthz { return 200 "ok\\n"; } location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf
EXPOSE 80