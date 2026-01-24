# Use Node.js as base image with bun
FROM oven/bun:1 as build-stage

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json bun.lock* ./

# Install project dependencies
RUN bun install --frozen-lockfile

# Copy project files
COPY . .

# Build application
RUN bun run build

# Use nginx as production environment image
FROM nginx:stable-alpine as production-stage

# Copy built files to nginx
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
