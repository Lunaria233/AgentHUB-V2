# Capability Contracts

This document freezes the core architecture contracts that should remain stable while the platform evolves from the current lightweight implementation to the full versions of Memory, Context Engineering, MCP, RAG, and Skills.

## Recommended architecture mode

Use **shared platform infrastructure + agent-level profile overrides + plugin registration**.

- Shared platform infrastructure owns storage, protocols, tracing, isolation, registration, and lifecycle.
- Agent applications own prompt policy, workflow stages, profile selection, and permissions.
- Plugins extend capabilities without changing the core runtime.

## Core contracts added in code

### App capability profiles

Code:
- `backend/app/platform/apps/profiles.py`
- `backend/app/platform/apps/manifest.py`

`AppManifest` now carries:

- `runtime_factory`: the runtime factory that should build the app
- `profiles`: grouped capability profiles for context, memory, rag, mcp, and skills

This allows new apps to declare *how* they want to use shared capabilities without re-implementing them.

### Runtime factory registry

Code:
- `backend/app/platform/runtime/factory.py`

This is the replacement target for the current orchestrator `if app_id == ...` branching.

The intended path is:

1. Register runtime factories
2. Manifest declares `runtime_factory`
3. Orchestrator resolves the factory and builds the runtime through a stable `RuntimeBuildContext`

### Capability service contracts

Code:
- `backend/app/platform/capabilities/contracts.py`

These interfaces define the shape of the “full” platform capabilities:

- `BaseMemoryManager`
- `BaseRAGService`
- `BaseMCPGateway`
- `BaseSkillRuntime`

They are intentionally service-first. Tools may be generated from them later, but they are not modeled as “just tools”.

## Boundary rules

### Platform-owned

- storage and isolation
- retrieval/index backends
- mcp transports and connection lifecycle
- context builder and providers
- tracing and permission enforcement

### Agent-owned

- workflow stage design
- context profile selection
- memory write policy
- rag scope and retrieval preferences
- mcp allowlists
- enabled skills

### Must remain isolated

- `app_id`
- `user_id`
- `session_id`
- `knowledge_scope`
- `memory_scope`
- `allowed_mcp_servers`

## What “full version” means in this project

### Memory

- multiple memory types
- write policy
- retrieval policy
- consolidation / promotion
- isolation
- traceability

### Context Engineering

- profile-based context assembly
- providers
- token budgeting
- selection and compression
- stage-aware context
- traceability

### MCP

- real transport
- server registry
- dynamic tool discovery
- permission filtering
- runtime integration

### RAG

- ingestion
- chunking
- embedding
- retrieval
- citation
- scope isolation

### Skills

- skill bundle schema
- registry
- runtime injection
- per-app bindings

## Next implementation path

1. Refactor orchestrator to consume `runtime_factory`
2. Make runtimes read their profile objects instead of hardcoded settings
3. Complete MCP end-to-end through `BaseMCPGateway`
4. Upgrade Memory and RAG behind the new contracts
5. Add skill resolution and injection
