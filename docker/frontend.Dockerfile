ARG NODE_IMAGE=node:24.22.0-alpine@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f
FROM ${NODE_IMAGE} AS deps
ARG APP_VERSION=1.10.0
LABEL org.opencontainers.image.title="venom-frontend" \
      org.opencontainers.image.version="${APP_VERSION}"
WORKDIR /app/web-next
COPY web-next/package.json web-next/package-lock.json ./
RUN npm ci

FROM ${NODE_IMAGE} AS builder
WORKDIR /app/web-next
COPY --from=deps /app/web-next/node_modules ./node_modules
COPY web-next ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM ${NODE_IMAGE} AS runner
WORKDIR /app/web-next
ARG APP_VERSION=1.10.0
LABEL org.opencontainers.image.title="venom-frontend" \
      org.opencontainers.image.version="${APP_VERSION}"
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY --from=builder /app/web-next/.next ./.next
COPY --from=builder /app/web-next/public ./public
COPY --from=builder /app/web-next/scripts ./scripts
COPY --from=builder /app/web-next/package.json ./package.json

EXPOSE 3000

CMD ["npm", "run", "start"]
