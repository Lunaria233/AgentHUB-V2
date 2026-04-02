---
name: tool_use_hygiene
display_name: Tool Use Hygiene
description: Encourage disciplined tool use and explicit tool-result handling.
tags:
  - tools
  - reliability
tools:
  - search
  - note
---
# Tool Use Hygiene

## Instructions
- Use tools only when they can materially improve correctness or reduce ambiguity.
- Do not claim a tool succeeded unless the returned payload confirms it.
- When a tool fails, report the failure briefly and continue with the best fallback.
- Prefer one decisive tool call over several low-value calls.

## Stage: chat.reply
- Summarize tool outputs rather than dumping raw tool payloads.

## Stage: research.plan
- Use tool calls to reduce uncertainty in plan assumptions, not to replace planning.
