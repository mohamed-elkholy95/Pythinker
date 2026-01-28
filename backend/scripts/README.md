# Backend Scripts

This directory contains utility scripts for database management and development.

## Database Management

### Initialize MongoDB Schema

Sets up all collections and indexes for the multi-task system:

```bash
# From backend directory
python scripts/init_mongodb.py
```

This creates:
- **Sessions collection** with multi-task, workspace, and budget indexes
- **Events collection** for event sourcing
- **Usage tracking collections** (usage_records, session_usage, daily_usage)
- **Session metrics collection** for monitoring
- **GridFS buckets** for screenshots and artifacts
- **Agent collections** for orchestration
- **Knowledge & datasource collections**

### Reset Development Database

**⚠️ DESTRUCTIVE**: Drops entire database and recreates schema.

```bash
# Option 1: Python script (recommended)
python scripts/reset_dev_db.py

# Option 2: Bash script
./scripts/reset_dev_db.sh
```

Both scripts will:
1. Ask for confirmation
2. Drop the database
3. Reinitialize all collections and indexes

**Use this when:**
- Starting fresh development
- Schema has changed significantly
- Need to clear all test data

## Development Workflow

### First Time Setup

1. Copy environment example:
   ```bash
   cp .env.example .env
   ```

2. Update MongoDB URI in `.env`:
   ```
   MONGODB_URI=mongodb://localhost:27017
   MONGODB_DATABASE=pythinker
   ```

3. Initialize database:
   ```bash
   python scripts/init_mongodb.py
   ```

4. Start development stack:
   ```bash
   cd ..
   ./dev.sh up -d
   ```

### Resetting During Development

If you need to clear data or reset schema:

```bash
python scripts/reset_dev_db.py
./dev.sh restart backend
```

## Schema Overview

### Collections Created

| Collection | Purpose | Key Indexes |
|------------|---------|-------------|
| `sessions` | User sessions with multi-task support | user_id, multi_task_challenge.id, budget_paused |
| `events` | Event sourcing for sessions | session_id, type, timestamp |
| `users` | User accounts | email (unique), username (unique) |
| `usage_records` | Individual LLM call tracking | user_id, session_id, created_at |
| `session_usage` | Aggregated session usage | session_id (unique), user_id |
| `daily_usage` | Daily rollups per user | user_id + date (unique) |
| `session_metrics` | Performance and activity metrics | session_id (unique), user_id |
| `agents` | Agent definitions | user_id, name |
| `knowledge` | Session knowledge | session_id, scope |
| `datasources` | API datasources | session_id, api_name |
| `screenshots.files` | GridFS screenshot metadata | session_id, task_id, capture_reason |
| `screenshots.chunks` | GridFS screenshot data | - |
| `artifacts.files` | GridFS artifact metadata | session_id, type |
| `artifacts.chunks` | GridFS artifact data | - |

### New Fields in Session Model

```python
# Multi-task challenge tracking
multi_task_challenge: Optional[MultiTaskChallenge] = None
workspace_structure: Optional[Dict[str, str]] = None

# Budget tracking
budget_limit: Optional[float] = None  # USD
budget_warning_threshold: float = 0.8
budget_paused: bool = False

# Execution metadata
iteration_limit_override: Optional[int] = None
complexity_score: Optional[float] = None  # 0.0-1.0
```

## GridFS Buckets

### Screenshots
- **Bucket**: `screenshots`
- **Purpose**: Store VNC screenshots from sandbox
- **Metadata**: session_id, task_id, capture_reason, timestamp
- **Format**: JPEG (compressed, quality=85)

### Artifacts
- **Bucket**: `artifacts`
- **Purpose**: Store workspace deliverables and files
- **Metadata**: session_id, type, filename
- **Format**: Various (files, archives, data)

## Troubleshooting

### Connection Failed

If you see "Failed to connect to MongoDB":

1. Check MongoDB is running:
   ```bash
   docker ps | grep mongo
   ```

2. Verify connection string in `.env`

3. For Docker MongoDB:
   ```bash
   docker-compose -f docker-compose-development.yml up -d mongodb
   ```

### Import Errors

If you see import errors when running scripts:

```bash
cd backend
export PYTHONPATH=$PWD:$PYTHONPATH
python scripts/init_mongodb.py
```

### Permission Denied

If scripts won't execute:

```bash
chmod +x scripts/*.sh
chmod +x scripts/*.py
```

## Notes

- All scripts use settings from `app.core.config`
- MongoDB connection is configured via environment variables
- Scripts are safe to run multiple times (idempotent)
- Indexes are dropped and recreated on each init
- GridFS buckets persist after collection drops
