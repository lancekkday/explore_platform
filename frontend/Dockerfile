# Stage 1: build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

# Default: served at root /
# EC2 subpath: docker-compose build with VITE_API_URL=/explore_platform/api VITE_BASE_URL=/explore_platform/
ARG VITE_API_URL=/api
ARG VITE_BASE_URL=/
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_BASE_URL=$VITE_BASE_URL
RUN npm run build

# Stage 2: serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
