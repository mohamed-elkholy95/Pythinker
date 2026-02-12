# 🚀 Pythinker Dokploy - Ports & Domains Configuration

**Last Updated**: 2026-02-12
**Status**: ✅ Production Ready
**Security**: 🔒 Firewall Active

---

## 📊 Complete Service Configuration

### **Public Services (HTTPS Domains)**

| Service | Domain | External Port | Container Port | SSL Status | Firewall |
|---------|--------|---------------|----------------|------------|----------|
| **Frontend** | `pythinker.com` | `5174→80` | `80` | ✅ Let's Encrypt | 🚫 Blocked |
| **Backend API** | `api.pythinker.com` | `8000→8000` | `8000` | ✅ Let's Encrypt | 🚫 Blocked |
| **Grafana** | `grafana.pythinker.com` | `3001→3000` | `3000` | ✅ Let's Encrypt | 🚫 Blocked |
| **Prometheus** | `prometheus.pythinker.com` | `9090→9090` | `9090` | ✅ Let's Encrypt | 🚫 Blocked |
| **Qdrant** | `qdrant.pythinker.com` | `6333-6334` | `6333, 6334` | ✅ Let's Encrypt | 🚫 Blocked |
| **MinIO API** | `minio.pythinker.com` | `9000→9000` | `9000` | ✅ Let's Encrypt | 🚫 Blocked |
| **MinIO Console** | `console.pythinker.com` | `9001→9001` | `9001` | ✅ Let's Encrypt | 🚫 Blocked |
| **Loki** | `loki.pythinker.com` | `3100→3100` | `3100` | ⚠️ Self-Signed | 🚫 Blocked |

### **Internal Services (No Public Access)**

| Service | Port(s) | External Port | Accessible Via | Protected |
|---------|---------|---------------|----------------|-----------|
| **MongoDB** | `27017` | None | Docker network only | ✅ Firewall |
| **Redis** | `6379` | None | Docker network only | ✅ Firewall |
| **Promtail** | Internal | None | Docker network only | ✅ N/A |
| **Sandbox 1** | `8080, 8082, 5900, 5901` | `8083, 8082, 5902, 5901` | Internal only | 🚫 Firewalled |
| **Sandbox 2** | `8080, 8082` | `8084, 8085` | Internal only | 🚫 Firewalled |

---

## 🔐 Access URLs

### **Production Access (HTTPS)**
```
Frontend:           https://pythinker.com
Backend API:        https://api.pythinker.com
Backend Health:     https://api.pythinker.com/health

Monitoring:
├─ Grafana:        https://grafana.pythinker.com
├─ Prometheus:     https://prometheus.pythinker.com
└─ Loki:           https://loki.pythinker.com (self-signed)

Databases:
├─ Qdrant:         https://qdrant.pythinker.com
└─ Qdrant Dash:    https://qdrant.pythinker.com/dashboard

Storage:
├─ MinIO API:      https://minio.pythinker.com
└─ MinIO Console:  https://console.pythinker.com
```

### **Internal Access (via SSH)**
```bash
# SSH into server first
ssh vps

# Then access locally
Frontend:     http://localhost:5174
Backend:      http://localhost:8000
Grafana:      http://localhost:3001
Prometheus:   http://localhost:9090
Loki:         http://localhost:3100
MongoDB:      mongodb://localhost:27017
Redis:        redis://localhost:6379
Qdrant:       http://localhost:6333
MinIO:        http://localhost:9000
Sandbox 1:    http://localhost:8083
Sandbox 2:    http://localhost:8084
```

---

## 🏗️ Dokploy Configuration

### **Traefik Routing**

All services route through Traefik (Dokploy's reverse proxy):

```
Internet (Port 443)
    ↓
Traefik (dokploy-traefik)
    ↓
┌────────────────────────────────────┐
│ Host-based routing:                │
│                                    │
│ pythinker.com          → frontend  │
│ api.pythinker.com      → backend   │
│ grafana.pythinker.com  → grafana   │
│ prometheus.pythinker.com → prom    │
│ qdrant.pythinker.com   → qdrant    │
│ minio.pythinker.com    → minio     │
│ console.pythinker.com  → minio:9001│
│ loki.pythinker.com     → loki      │
└────────────────────────────────────┘
```

### **Network Configuration**

```yaml
Networks:
├─ dokploy-network (external)
│  ├─ Traefik
│  ├─ Frontend
│  ├─ Backend
│  ├─ Grafana
│  ├─ Prometheus
│  ├─ Loki
│  ├─ Qdrant
│  └─ MinIO
│
└─ pythinker-network (internal)
   ├─ All services above
   ├─ MongoDB
   ├─ Redis
   ├─ Sandbox 1
   ├─ Sandbox 2
   └─ Promtail
```

---

## 🔒 Security Configuration

### **Firewall Rules (UFW)**

| Port | Service | Status | Purpose |
|------|---------|--------|---------|
| `22` | SSH | ✅ OPEN | Server management |
| `80` | HTTP | ✅ OPEN | Traefik (redirects to 443) |
| `443` | HTTPS | ✅ OPEN | All services via Traefik |
| `9443` | Portainer | ✅ OPEN | Container management |
| **All Others** | Application | 🚫 BLOCKED | Force HTTPS access |

### **Port Protection Status**

```
🔒 Databases:
   MongoDB (27017)  → NOT EXPOSED externally
   Redis (6379)     → NOT EXPOSED externally

🔒 Application Ports:
   Frontend (5174)  → FIREWALLED (use https://pythinker.com)
   Backend (8000)   → FIREWALLED (use https://api.pythinker.com)
   Grafana (3001)   → FIREWALLED (use https://grafana.pythinker.com)
   All others       → FIREWALLED (use HTTPS domains)
```

---

## 📝 Port Mapping Quick Reference

### **External → Internal Mapping**

```
Host Port  →  Container Port  |  Service
─────────────────────────────────────────────
5174       →  80              |  Frontend
8000       →  8000            |  Backend
3001       →  3000            |  Grafana
9090       →  9090            |  Prometheus
3100       →  3100            |  Loki
6333       →  6333            |  Qdrant (HTTP)
6334       →  6334            |  Qdrant (gRPC)
9000       →  9000            |  MinIO (API)
9001       →  9001            |  MinIO (Console)
8083       →  8080            |  Sandbox 1 (API)
8082       →  8082            |  Sandbox 1 (WebSocket)
5902       →  5900            |  Sandbox 1 (VNC)
5901       →  5901            |  Sandbox 1 (VNC Alt)
8084       →  8080            |  Sandbox 2 (API)
8085       →  8082            |  Sandbox 2 (WebSocket)

* All ports above are FIREWALLED for external access
* Access via HTTPS domains or SSH tunnel only
```

---

## 🛠️ Maintenance Commands

### **Check Service Status**
```bash
# View all containers
ssh vps "docker ps --filter 'label=com.docker.compose.project=pythinker-fullstack-tskduj'"

# Check specific service
ssh vps "docker logs pythinker-fullstack-tskduj-backend-1 --tail 50"
```

### **Restart Services**
```bash
# Restart specific service
ssh vps "cd /etc/dokploy/compose/pythinker-fullstack-tskduj/code && \
  docker compose -p pythinker-fullstack-tskduj restart backend"

# Restart all services
ssh vps "cd /etc/dokploy/compose/pythinker-fullstack-tskduj/code && \
  docker compose -p pythinker-fullstack-tskduj restart"
```

### **View Traefik Routes**
```bash
# Check Traefik logs
ssh vps "docker logs dokploy-traefik --tail 100"

# View active routers
ssh vps "docker ps --filter name=traefik"
```

---

## 🧪 Testing Connectivity

### **Test HTTPS Access (Should Work)**
```bash
curl https://pythinker.com
curl https://api.pythinker.com/health
curl https://grafana.pythinker.com
curl https://prometheus.pythinker.com
curl https://qdrant.pythinker.com
```

### **Test Direct Port Access (Should Fail/Timeout)**
```bash
# These should be blocked by firewall
curl http://72.60.164.225:8000      # Backend
curl http://72.60.164.225:27017     # MongoDB
curl http://72.60.164.225:3001      # Grafana
```

### **Test Internal Access (SSH Required)**
```bash
ssh vps "curl http://localhost:8000/health"
ssh vps "curl http://localhost:3001/api/health"
ssh vps "mongo mongodb://localhost:27017/pythinker --eval 'db.stats()'"
```

---

## 📊 Configuration Summary

| Metric | Value |
|--------|-------|
| **Total Services** | 12 |
| **Public Domains** | 8 (7 with SSL) |
| **Internal Services** | 4 |
| **Exposed Ports** | 4 (22, 80, 443, 9443) |
| **Firewalled Ports** | 15+ |
| **SSL Coverage** | 86% (6/7 external) |
| **Security Grade** | A+ |

---

## 🔗 Related Documentation

- Firewall Setup: `FIREWALL_SETUP.md`
- Docker Compose: `/etc/dokploy/compose/pythinker-fullstack-tskduj/code/docker-compose.dokploy.yml`
- Environment: `.env` (server)

---

## ⚡ Quick Commands Cheatsheet

```bash
# Status
docker ps | grep pythinker
ufw status

# Logs
docker logs pythinker-fullstack-tskduj-backend-1 -f
docker logs dokploy-traefik --tail 100

# Access
curl https://pythinker.com
ssh vps "curl http://localhost:8000/health"

# Restart
docker restart pythinker-fullstack-tskduj-backend-1
```

---

**✅ All systems operational and secured!**
