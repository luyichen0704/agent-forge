# agent-forge web (frontend) — build the SPA, serve via nginx
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY deploy/nginx/web.docker.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
