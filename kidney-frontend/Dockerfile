FROM node:22-slim AS build

WORKDIR /app

# Install from the lockfile before copying source so this layer only
# reinvalidates when dependencies actually change, not on every source edit.
COPY package.json package-lock.json ./
# `npm ci` (not used here) fails in this Linux container: package-lock.json
# was generated on Windows, and npm only records the optional native
# binary variant(s) for the platform it ran on (e.g. lightningcss/rolldown's
# win32 build) -- the Linux-specific optional deps (e.g. @emnapi/runtime)
# are simply absent from the lock file, which `npm ci`'s strict
# lockfile-must-match-exactly mode treats as an error. `npm install`
# resolves and adds whatever the current platform actually needs instead of
# hard-failing on that gap. Confirmed 2026-08-21 by testing both against
# this lockfile in a node:22-slim container.
RUN npm install

COPY . .

# Vite inlines VITE_-prefixed env vars into the built JS at build time, not
# runtime -- there's no server-side process to read an env var from once
# this is static files behind nginx. Must be passed as a build ARG.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
