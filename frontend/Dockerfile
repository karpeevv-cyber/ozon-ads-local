FROM node:22-alpine AS deps

WORKDIR /app

COPY frontend/package.json /app/package.json
COPY frontend/package-lock.json /app/package-lock.json

RUN npm ci


FROM node:22-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules /app/node_modules
COPY frontend/package.json /app/package.json
COPY frontend/tsconfig.json /app/tsconfig.json
COPY frontend/next.config.ts /app/next.config.ts
COPY frontend/next-env.d.ts /app/next-env.d.ts
COPY frontend/src /app/src

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build


FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/.next/standalone /app/
COPY --from=builder /app/.next/static /app/.next/static

EXPOSE 3000

CMD ["node", "server.js"]
