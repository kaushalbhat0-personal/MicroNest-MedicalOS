# P7 preview/production web image (npm workspaces monorepo).
# Build-time public config only (NEXT_PUBLIC_API_URL); no secrets baked in.
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000

FROM node:22-alpine AS build
WORKDIR /srv/app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/ui/package.json packages/ui/package.json
RUN npm ci --no-audit --no-fund
COPY apps/web apps/web
COPY packages/ui packages/ui
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build -w @healthcare-os/web

FROM node:22-alpine AS run
WORKDIR /srv/app
ENV NODE_ENV=production
RUN adduser -D -u 10001 app
COPY --from=build --chown=app /srv/app/node_modules ./node_modules
COPY --from=build --chown=app /srv/app/apps/web/.next ./apps/web/.next
COPY --from=build --chown=app /srv/app/apps/web/public ./apps/web/public
COPY --from=build --chown=app /srv/app/apps/web/package.json ./apps/web/package.json
COPY --from=build --chown=app /srv/app/packages/ui ./packages/ui
COPY --from=build --chown=app /srv/app/package.json ./package.json
USER app
EXPOSE 3000
CMD ["npm", "run", "start", "-w", "@healthcare-os/web"]
