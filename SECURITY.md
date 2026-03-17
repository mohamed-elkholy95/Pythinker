# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, report vulnerabilities privately:

1. **Email**: Send details to **melkholy@techmatrix.com**
2. **Include**: Description of the vulnerability, steps to reproduce, potential impact, and suggested fix if any

### What to Expect

- **Acknowledgment** within 48 hours
- **Assessment** within 1 week
- **Fix or mitigation** for confirmed vulnerabilities as soon as possible
- **Credit** in the release notes (unless you prefer anonymity)

## Security Architecture

Pythinker uses several layers of security:

- **Sandboxed execution** — All agent tasks run in isolated Docker containers with resource limits
- **Container hardening** — `no-new-privileges`, `cap_drop: ALL`, minimal capabilities
- **Network isolation** — Internal services (MongoDB, Redis, Qdrant) run on private Docker networks
- **JWT authentication** — Secure session management
- **Secret scanning** — CI pipeline includes TruffleHog and dependency auditing
- **No direct sandbox access** — All browser/terminal access is proxied through authenticated backend endpoints

## Best Practices for Deployment

- Always change default secrets in `.env` before deploying
- Use TLS termination (Traefik/nginx) in production
- Keep Docker images updated
- Monitor container logs for anomalous behavior
- Restrict network access to management ports (MongoDB, Redis, MinIO)
