# Use nginx as production environment image
FROM nginx:stable-alpine AS production-stage

# Copy pre-built files to nginx (build locally with: bun run build)
COPY dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf.template

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose port 80
EXPOSE 80

# Start nginx with environment variable substitution
CMD ["/docker-entrypoint.sh"]
