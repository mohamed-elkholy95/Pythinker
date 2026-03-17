SAMPLE_RESEARCH_REPORT = """# AI Agent Architectures: A Comprehensive Analysis

## Executive Summary

The landscape of AI agent architectures has evolved significantly in 2025, with several key frameworks emerging as leaders in multi-agent orchestration, tool use, and autonomous task completion.

## Key Frameworks

### 1. Legacy Flow
Legacy Flow provides a graph-based approach to building stateful, multi-agent systems. Key features include:
- **Cyclic graph execution** for complex workflows
- **Built-in persistence** with checkpoint system
- **Human-in-the-loop** support for critical decisions

### 2. CrewAI
CrewAI focuses on role-based agent collaboration:
- **Role assignment** with specialized agents
- **Task delegation** and sequential/parallel execution
- **Memory sharing** between agents

### 3. AutoGen
Microsoft's AutoGen emphasizes conversational agent patterns:
- **Multi-agent conversations** with flexible topologies
- **Code execution** in sandboxed environments
- **Teachability** for agent learning

## Architecture Patterns

### Plan-Act-Reflect
The most common pattern involves three phases:
1. **Planning**: Decompose task into actionable steps
2. **Acting**: Execute steps using available tools
3. **Reflecting**: Evaluate results and adjust

### ReAct (Reasoning + Acting)
Interleaving reasoning with actions for more reliable task completion.

## Recommendations

For production systems, we recommend:
- Use **Legacy Flow** for complex, stateful workflows
- Use **CrewAI** for team-based task delegation
- Implement **circuit breakers** for tool execution
- Add **human oversight** for high-stakes decisions

## Sources

1. Legacy Flow Documentation (2025)
2. CrewAI Framework Guide (2025)
3. AutoGen Research Paper (Microsoft, 2025)
"""

SAMPLE_CODE_REPORT = """# FastAPI Todo Application

## Overview

A complete REST API implementation for task management built with FastAPI and Python.

## Features

- Full CRUD operations for todo items
- Pydantic v2 model validation
- Async SQLAlchemy with PostgreSQL
- JWT authentication
- Automatic OpenAPI documentation

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /todos | List all todos |
| POST | /todos | Create a todo |
| GET | /todos/{id} | Get a todo |
| PUT | /todos/{id} | Update a todo |
| DELETE | /todos/{id} | Delete a todo |

## Getting Started

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```
"""
