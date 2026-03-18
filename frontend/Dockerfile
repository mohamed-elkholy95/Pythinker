# Build stage: compile frontend from source so image never depends on local dist state
FROM node:22-slim AS build-stage

WORKDIR /app
# Vite build for this bundle can exceed 2 GB old-space in CI; keep headroom configurable.
ARG NODE_MAX_OLD_SPACE_SIZE=3072
ENV NODE_OPTIONS=--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE}

# Install dependencies first for better layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy source files and build
COPY . .
RUN npm run build

# Production stage: serve compiled assets with nginx
FROM nginx:stable-alpine AS production-stage

ARG GIT_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="pythinker-frontend"
LABEL org.opencontainers.image.version=${GIT_VERSION}
LABEL org.opencontainers.image.revision=${GIT_SHA}
LABEL org.opencontainers.image.created=${BUILD_DATE}
LABEL org.opencontainers.image.source="https://github.com/mohamed-elkholy95/Pythinker"

ENV GIT_VERSION=${GIT_VERSION}
ENV GIT_SHA=${GIT_SHA}
ENV BUILD_DATE=${BUILD_DATE}

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
