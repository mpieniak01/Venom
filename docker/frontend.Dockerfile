FROM node:20-alpine AS deps
WORKDIR /app/web-next
COPY web-next/package.json web-next/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app/web-next
COPY --from=deps /app/web-next/node_modules ./node_modules
COPY web-next ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app/web-next
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
