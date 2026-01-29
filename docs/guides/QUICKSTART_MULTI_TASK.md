# Quick Start: Multi-Task System

## Prerequisites

- Docker and Docker Compose installed
- MongoDB running (via Docker or local)
- Python 3.10+ installed

## Step-by-Step Setup

### 1. Clone and Navigate

```bash
cd /Users/panda/Desktop/Projects/pythinker
```

### 2. Set Up Backend Environment

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy example environment
cp .env.example .env

# Edit .env and set MongoDB connection
# Default values should work for Docker setup:
# MONGODB_URI=mongodb://mongodb:27017
# MONGODB_DATABASE=pythinker
```

### 4. Initialize Database

```bash
# Initialize MongoDB schema with all indexes
python scripts/init_mongodb.py
```

Expected output:
```
✅ Connected to MongoDB
✅ Sessions collection configured
✅ Events collection configured
✅ Users collection configured
✅ Usage tracking collections configured
✅ Session metrics collection configured
✅ GridFS buckets configured
✅ Agent collections configured
✅ Knowledge collections configured

MongoDB Schema Initialization Complete!
Database: pythinker
Collections created: 14
✅ MongoDB is ready for development!
```

### 5. Verify Imports

```bash
# Test that all new modules load correctly
python scripts/test_imports.py
```

Expected output:
```
Testing imports for multi-task system...

1. Testing domain models...
   ✅ multi_task models
   ✅ new event types
   ✅ SessionMetrics
   ✅ updated Session model

2. Testing services...
   ✅ ContextManager
   ✅ ComplexityAssessor
   ✅ CommandFormatter
   ✅ Workspace services
   ✅ ResearchAgent

3. Testing infrastructure...
   ✅ MongoDB with GridFS

==================================================
Tests passed: 10
Tests failed: 0
==================================================

✅ All imports successful!
```

### 6. Start Development Stack

```bash
cd ..  # Back to project root
./dev.sh up -d
```

This starts:
- Backend (FastAPI) on port 8000
- Frontend (Vue 3) on port 5173
- MongoDB on port 27017
- Redis on port 6379
- Sandbox containers as needed

### 7. Verify Services

```bash
# Check all containers are running
docker ps

# Check backend logs
./dev.sh logs -f backend

# Check MongoDB connection
docker exec -it pythinker-mongodb-1 mongosh --eval "db.adminCommand('ping')"
```

### 8. Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Using the Multi-Task System

### Creating a Multi-Task Challenge

```python
from app.domain.models.multi_task import (
    MultiTaskChallenge,
    TaskDefinition,
    Deliverable,
    DeliverableType,
    TaskStatus,
)

# Define tasks
challenge = MultiTaskChallenge(
    title="Research and Analysis Project",
    description="Conduct research and create analysis report",
    workspace_template="research",
    tasks=[
        TaskDefinition(
            title="Gather Information",
            description="Research machine learning techniques",
            deliverables=[
                Deliverable(
                    name="sources.md",
                    type=DeliverableType.FILE,
                    path="/workspace/deliverables/sources.md",
                    description="Bibliography of sources",
                )
            ],
        ),
        TaskDefinition(
            title="Create Report",
            description="Synthesize findings into report",
            deliverables=[
                Deliverable(
                    name="report.pdf",
                    type=DeliverableType.FILE,
                    path="/workspace/deliverables/report.pdf",
                    description="Final research report",
                )
            ],
        ),
    ],
)
```

### Using Workspace Templates

```python
from app.domain.services.workspace import (
    WorkspaceSelector,
    get_template,
)

# Auto-select template based on task
selector = WorkspaceSelector()
template = selector.select_template("Research machine learning algorithms")
# Returns: research template

# Or get specific template
template = get_template("data_analysis")
```

### Using Context Manager

```python
from app.domain.services.agents.context_manager import ContextManager

# Initialize
context = ContextManager(max_context_tokens=8000)

# Track file operations
context.track_file_operation(
    path="/workspace/data.csv",
    operation="created",
    content_summary="Dataset with 1000 rows",
)

# Track tool executions
context.track_tool_execution(
    tool_name="browser_navigate",
    summary="Browsed wikipedia for ML algorithms",
    key_findings=["Neural networks are popular", "SVMs for classification"],
)

# Get context summary for prompt injection
summary = context.get_context_summary()
# Returns prioritized markdown summary
```

### Assessing Task Complexity

```python
from app.domain.services.agents.complexity_assessor import ComplexityAssessor

assessor = ComplexityAssessor()
assessment = assessor.assess_task_complexity(
    task_description="Build a full-stack web application with authentication",
    plan_steps=12,
    is_multi_task=True,
)

print(assessment.category)  # "very_complex"
print(assessment.recommended_iterations)  # 300
print(assessment.reasoning)  # Detailed explanation
```

### Formatting Commands for UI

```python
from app.domain.services.tools.command_formatter import CommandFormatter

display, category, summary = CommandFormatter.format_tool_call(
    tool_name="search_web",
    function_name="search_web",
    function_args={"query": "machine learning"},
)

print(display)    # "Searching 'machine learning'"
print(category)   # "search"
print(summary)    # "Search: machine learning"
```

## Development Workflow

### Making Changes

1. Edit code in `backend/app/`
2. Backend auto-reloads with FastAPI/uvicorn
3. Frontend auto-reloads with Vite

### Resetting Database

If you need to start fresh:

```bash
cd backend
python scripts/reset_dev_db.py
# Type 'yes' to confirm
```

### Viewing Logs

```bash
# All services
./dev.sh logs -f

# Specific service
./dev.sh logs -f backend
./dev.sh logs -f frontend
./dev.sh logs -f mongodb
```

### Stopping Services

```bash
# Stop all
./dev.sh down

# Stop and remove volumes (nuclear option)
./dev.sh down -v
```

## Troubleshooting

### Import Errors

```bash
# Make sure you're in backend directory with venv activated
cd backend
source .venv/bin/activate
export PYTHONPATH=$PWD:$PYTHONPATH
```

### MongoDB Connection Failed

```bash
# Check MongoDB is running
docker ps | grep mongo

# Restart MongoDB
./dev.sh restart mongodb

# Check MongoDB logs
./dev.sh logs mongodb
```

### Port Already in Use

```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or change port in docker-compose-development.yml
```

### GridFS Errors

```bash
# Reinitialize GridFS buckets
cd backend
python scripts/init_mongodb.py
```

## Next Steps

1. **Explore the API**: Visit http://localhost:8000/docs
2. **Create a Session**: POST to `/api/v1/sessions`
3. **Test Multi-Task**: Create a multi-task challenge via API
4. **Monitor Events**: Watch SSE stream for real-time events
5. **Check Workspace**: Inspect created workspace structure

## Additional Resources

- **Implementation Summary**: See `MULTI_TASK_IMPLEMENTATION_SUMMARY.md`
- **Database Scripts**: See `backend/scripts/README.md`
- **Development Guide**: See `CLAUDE.md`
- **API Documentation**: http://localhost:8000/docs (when running)
