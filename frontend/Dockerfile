# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Same-origin in production: the API is at /api on the same host.
ENV VITE_API_URL=""
RUN npm run build

FROM nginx:1.28-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/snippets/ /etc/nginx/snippets/
COPY --from=build /app/dist /usr/share/nginx/html
