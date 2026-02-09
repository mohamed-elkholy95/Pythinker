# Build stage: compile frontend from source so image never depends on local dist state
FROM node:22-slim AS build-stage

WORKDIR /app
# Constrain Vite/Node heap to avoid OOM kills in constrained Docker environments.
ENV NODE_OPTIONS=--max-old-space-size=2048

# Install dependencies first for better layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy source files and build
COPY . .
RUN npm run build

# Production stage: serve compiled assets with nginx
FROM nginx:stable-alpine AS production-stage

# Copy build output from builder stage
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf.template

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose port 80
EXPOSE 80

# Start nginx with environment variable substitution
CMD ["/docker-entrypoint.sh"]
