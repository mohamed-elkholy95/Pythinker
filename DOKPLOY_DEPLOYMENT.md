# Dokploy Deployment Guide for Pythinker

Complete guide for deploying Pythinker's full multi-service architecture on Dokploy.

## Why Docker Compose for Pythinker?

✅ **Multi-Service Architecture**: 9 services (Frontend, Backend, MongoDB, Redis, Qdrant, MinIO, 2x Sandbox)
✅ **Native Docker Compose Support**: Dokploy manages all services with individual monitoring
✅ **Self-Hosted**: Aligns with Pythinker's self-hosted first principle
✅ **Automated Backups**: Dokploy supports volume backups for databases
✅ **Auto-Deploy**: GitHub webhook integration for automatic deployments

---

## Prerequisites

### Server Requirements
- **RAM**: Minimum 8GB (16GB recommended for production)
- **Disk**: 50GB+ free space
- **CPU**: 4+ cores recommended
- **OS**: Linux with Docker installed

### Dokploy Installation
```bash
curl -sSL https://dokploy.com/install.sh | sh
```

After installation, access Dokploy at: `http://YOUR_SERVER_IP:3000`

---

## Deployment Steps

### Step 1: Create New Compose Project

1. Log into Dokploy dashboard
2. Click **"Create Project"** → Select **"Docker Compose"**
3. Name: `pythinker`
4. Repository: `https://github.com/Planko123/Pythinker.git`
5. Branch: `main`
6. Compose File Path: `docker-compose.dokploy.yml`

### Step 2: Configure Environment Variables

In Dokploy's **Environment** tab, add these variables:

```env
# LLM Configuration (REQUIRED)
LLM_PROVIDER=openai
API_KEY=your-kimi-or-openai-key
API_BASE=https://api.kimi.com/coding/v1
MODEL_NAME=kimi-for-coding
TEMPERATURE=0.6
MAX_TOKENS=16384

# Embedding Configuration (REQUIRED)
EMBEDDING_API_KEY=your-openai-key
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small

# Search API Keys (REQUIRED)
SERPER_API_KEY=your-serper-key
SERPER_API_KEY_2=your-serper-key-2
SERPER_API_KEY_3=your-serper-key-3
TAVILY_API_KEY=your-tavily-key
SEARCH_PROVIDER=serper

# JWT Security (REQUIRED - generate random 64-char string)
JWT_SECRET_KEY=your-64-char-random-string

# Auth Configuration
AUTH_PROVIDER=none
LOCAL_AUTH_EMAIL=admin@pythinker.com
LOCAL_AUTH_PASSWORD=admin*123

# CORS (Update with your domain)
CORS_ORIGINS=http://localhost:5174,https://your-domain.com

# Optional: Monitoring
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=your-secure-password

# Logging
LOG_LEVEL=INFO
```

**Note**: Dokploy will automatically create a `.env` file from these variables.

### Step 3: Configure Volumes (Advanced Tab)

Dokploy automatically manages these volumes:
- `mongodb_data` - MongoDB database
- `qdrant_data` - Vector database
- `minio_data` - File storage

Enable **Volume Backups** in Dokploy for automated database backups.

### Step 4: Deploy

1. Click **"Deploy"** button
2. Monitor build progress in the **Deployments** tab
3. Check service health in **Monitoring** tab

---

## Service Architecture

### Services Overview

| Service | Port | Purpose |
|---------|------|---------|
| **frontend** | 5174 | Vue.js UI |
| **backend** | 8000 | FastAPI server |
| **sandbox** | 8083 | Isolated task execution (primary) |
| **sandbox2** | 8084 | Isolated task execution (secondary) |
| **mongodb** | 27017 | Document database |
| **redis** | 6379 | Cache & sessions |
| **qdrant** | 6333/6334 | Vector database (semantic search) |
| **minio** | 9000/9001 | S3-compatible file storage |
| **prometheus** | 9090 | Metrics collection & alerting |
| **grafana** | 3001 | Monitoring dashboards |
| **loki** | 3100 | Log aggregation |
| **promtail** | - | Log shipper (no exposed port) |

### Resource Allocation

**Total Resources Needed:**
- Memory: ~14GB (3GB per sandbox + 4GB backend + 2GB databases + 3GB monitoring)
- CPU: 4+ cores (6+ recommended with monitoring)
- Disk: 50GB+ (30GB app + 20GB monitoring/logs)

---

## Post-Deployment Configuration

### Step 1: Configure Domain (Optional)

1. Go to **Domains** tab in Dokploy
2. Add your domain pointing to frontend service (port 5174)
3. Enable SSL/TLS with Let's Encrypt

### Step 2: Setup GitHub Auto-Deploy

1. In Dokploy, go to **General** → **Webhooks**
2. Copy the webhook URL
3. In GitHub repository settings:
   - Go to **Settings** → **Webhooks** → **Add webhook**
   - Paste Dokploy webhook URL
   - Select **"Just the push event"**
   - Click **Add webhook**

Now every `git push` to `main` will auto-deploy!

### Step 3: Verify Services

Check each service is healthy:

```bash
# Via Dokploy CLI (if installed on server)
docker ps | grep pythinker

# Or check Dokploy Monitoring tab
# All services should show green health status
```

### Step 4: Access Application

- **Frontend**: `http://YOUR_SERVER_IP:5174` (or your domain)
- **Backend API**: `http://YOUR_SERVER_IP:8000/docs` (Swagger UI)
- **MinIO Console**: `http://YOUR_SERVER_IP:9001` (admin/minioadmin)
- **Grafana Dashboard**: `http://YOUR_SERVER_IP:3001` (admin/your-password)
- **Prometheus**: `http://YOUR_SERVER_IP:9090`
- **Loki**: `http://YOUR_SERVER_IP:3100`

---

## Monitoring & Logs

### Grafana Dashboards

Access comprehensive monitoring at `http://YOUR_SERVER_IP:3001`:

**Pre-configured Dashboards:**
1. **Agent Performance** - LLM calls, tool execution, step durations
2. **System Health** - CPU, memory, disk, network per service
3. **Error Tracking** - Tool failures, stuck detections, validation errors
4. **Sandbox Pool** - Container lifecycle, warmup times, resource usage

**Log Analysis (Loki):**
- Use Grafana Explore to query logs with LogQL
- Example: `{container_name="pythinker-backend-1"} |= "error"`
- All container logs automatically collected by Promtail

### View Service Logs (Dokploy)

In Dokploy dashboard:
1. Click **Logs** tab
2. Select service (backend, frontend, sandbox, etc.)
3. View real-time or historical logs

**Or use Grafana Loki** for advanced log querying and correlation.

### Health Checks

All services include health checks:
- **Backend**: `GET /api/v1/health`
- **Sandbox**: `GET /health`
- **MongoDB**: Connection test
- **Redis**: Ping test
- **Qdrant**: TCP connection
- **Prometheus**: `GET /-/healthy`
- **Grafana**: `GET /api/health`
- **Loki**: `GET /ready`

---

## Troubleshooting

### Issue: Backend Can't Access Docker Socket

**Symptom**: Sandbox creation fails with "Cannot connect to Docker daemon"

**Fix**: Ensure Dokploy host has `/var/run/docker.sock` accessible:
```bash
# On Dokploy host
sudo chmod 666 /var/run/docker.sock
```

**Permanent fix**: Add to Dokploy advanced settings or docker-compose:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

### Issue: Sandbox Fails to Start

**Symptom**: Sandbox service shows unhealthy

**Fix**: Increase shared memory:
```yaml
shm_size: '2gb'  # Instead of 1gb
```

### Issue: Out of Memory

**Symptom**: Services crash or become unresponsive

**Fix**: Reduce sandbox pool size:
```env
SANDBOX_POOL_MAX_SIZE=1  # Instead of 2
SANDBOX_MEM_LIMIT=2g      # Instead of 3g
```

### Issue: Frontend Shows "Network Error"

**Symptom**: Frontend can't reach backend

**Fix**: Update CORS in environment variables:
```env
CORS_ORIGINS=http://YOUR_DOMAIN:5174,http://YOUR_IP:5174
```

---

## Scaling & Production

### Horizontal Scaling

To scale services in Dokploy:
1. Use Docker Swarm mode (requires Stack instead of Compose)
2. Or deploy multiple Dokploy instances with load balancer

### Production Checklist

- [ ] Change default passwords (MinIO, MongoDB, Admin)
- [ ] Enable HTTPS with Let's Encrypt
- [ ] Configure volume backups (Dokploy Backups feature)
- [ ] Set up monitoring alerts
- [ ] Review resource limits
- [ ] Enable rate limiting in backend
- [ ] Secure API keys in Dokploy secrets
- [ ] Configure firewall rules

---

## Backup & Recovery

### Automated Backups (Dokploy)

1. Go to **Volumes** tab
2. Enable **Volume Backups** for:
   - `mongodb_data` (critical)
   - `qdrant_data` (critical)
   - `minio_data` (critical)
   - `prometheus_data` (optional - metrics)
   - `grafana_data` (optional - dashboards)
   - `loki_data` (optional - logs)
3. Set backup schedule (daily recommended for critical, weekly for monitoring)

### Manual Backup

```bash
# MongoDB
docker exec pythinker-mongodb mongodump --out=/backup
docker cp pythinker-mongodb:/backup ./mongodb-backup

# Qdrant
docker cp pythinker-qdrant:/qdrant/storage ./qdrant-backup

# MinIO
docker exec pythinker-minio mc mirror /data ./minio-backup
```

---

## Migration from Railway

If you're migrating from Railway:

1. Export environment variables from Railway
2. Copy to Dokploy Environment tab
3. Deploy on Dokploy
4. Update DNS to point to new server
5. Verify all services healthy
6. Decommission Railway deployment

---

## Additional Resources

- **Dokploy Docs**: https://docs.dokploy.com/docs/core
- **Docker Compose Docs**: https://docs.dokploy.com/docs/core/docker-compose
- **Pythinker Docs**: See `CLAUDE.md` and `docs/` directory
- **Support**: Create issue on GitHub

---

## Quick Commands

```bash
# View all services
docker ps | grep pythinker

# View logs
docker logs pythinker-backend-1 -f
docker logs pythinker-frontend-1 -f

# Restart service
docker restart pythinker-backend-1

# Check resource usage
docker stats

# Access MongoDB
docker exec -it pythinker-mongodb mongo

# Access Redis
docker exec -it pythinker-redis redis-cli

# Health check all services
curl http://localhost:8000/api/v1/health
curl http://localhost:8083/health
```

---

## Next Steps

1. ✅ Deploy to Dokploy
2. ✅ Configure environment variables
3. ✅ Set up domain & SSL
4. ✅ Enable GitHub auto-deploy
5. ✅ Configure volume backups
6. ✅ Test all services
7. ✅ Monitor resource usage
8. ✅ Update documentation

**Deployment complete!** 🚀

For questions or issues, check Dokploy's monitoring logs or create a GitHub issue.
