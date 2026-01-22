# Pythinker - AI Agent System

Project URL: <https://github.com/mohamed-elkholy95/Pythinker-ai-agent>

---

Pythinker is a general-purpose AI Agent system that can be fully privately deployed and supports running various tools and operations in a sandbox environment.

The goal of Pythinker is to become a fully privately deployable enterprise-level AI agent application. Vertical AI agent applications have many repetitive engineering tasks, and this project hopes to unify this part, allowing everyone to build vertical AI agent applications like building blocks.

Each service and tool in Pythinker includes a Built-in version that can be fully privately deployed. Later, through A2A and MCP protocols, both Built-in Agents and Tools can be replaced. The underlying infrastructure can also be replaced by providing diverse provider configurations or simple development adaptations. Pythinker supports distributed multi-instance deployment from the architectural design, facilitating horizontal scaling to meet enterprise-level deployment requirements.

---

## Core Features

 * **Deployment:** Only requires one LLM service for deployment, no dependency on other external services.
 * **Tools:** Supports Terminal, Browser, File, Web Search, message tools, with real-time viewing and takeover capabilities.
 * **Sandbox:** Each Task is allocated a separate sandbox that runs in a local Docker environment.
 * **Task Sessions:** Manages session history through Mongo/Redis, supports background tasks.
 * **Conversations:** Supports stopping and interruption, supports file upload and download.
 * **Authentication:** User login and authentication.

## Author

Mohamed Elkholy
