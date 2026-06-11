# --- build stage ---
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
# Optional: bake a separate API origin into the bundle. Default "" keeps requests
# relative (/v1/...), served same-origin via the nginx proxy below.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# --- serve stage ---
FROM nginx:1.27-alpine
# API_UPSTREAM and PORT are substituted into the nginx config at container start
# by the base image's envsubst step. Defaults suit the compose stack; a PaaS
# overrides PORT (the port it routes to) and API_UPSTREAM (the API's address).
ENV API_UPSTREAM=api:8000
ENV PORT=80
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
