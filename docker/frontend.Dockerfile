# ---------- Frontend: build با Vite و سرو با Nginx (همچنین Reverse Proxy پنل) ----------
FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime

RUN apk add --no-cache curl tar

COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY installer/ /srv/installer/
COPY agent/ /srv/agent-src/
COPY tunnel-assets/ /srv/tunnel-assets/

# بسته Agent برای دستور نصب یک‌خطی روی سرورهای دیگر
RUN mkdir -p /srv/public \
    && tar -czf /srv/public/agent-bundle.tar.gz -C /srv agent-src \
    && cp /srv/installer/install-agent.sh /srv/public/install-agent.sh \
    && tar -czf /srv/public/tunnel-assets.tar.gz -C /srv tunnel-assets \
    && cp -r /srv/tunnel-assets /srv/public/tunnel-assets \
    && chmod 644 /srv/public/agent-bundle.tar.gz /srv/public/install-agent.sh /srv/public/tunnel-assets.tar.gz \
    && chmod 755 /srv/public/tunnel-assets \
    && chmod 644 /srv/public/tunnel-assets/*

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://127.0.0.1/health || exit 1
