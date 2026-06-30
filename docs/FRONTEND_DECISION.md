# Frontend Decision

Status: static preview

The included frontend is a static local artifact viewer. It is not API-backed and does not run CLI commands.

## Why Not API-Backed

An API-backed frontend would need a local server boundary, request validation, file access controls, generated-output cleanup, and separate frontend smoke coverage. That is larger than the current scope, which is a CLI-first deterministic toolkit.

## Current Promise

- Preview local JSON and Markdown artifacts.
- Help users inspect candidate, acquisition, analysis, and package outputs.
- Store only lightweight session metadata; file contents are not persisted.

## Non-Promise

- No hosted service.
- No local API server.
- No command execution.
- No external model calls.
- No autonomous source acquisition.

A future release can decide whether to add a local API. Until then, the product path is CLI-first with a static artifact viewer.
