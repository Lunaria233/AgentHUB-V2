# Skills Architecture

`AgentHub` treats skills as a platform capability, not just a prompt constant.

## Design

- `SkillBundle`: reusable capability package with description, prompt fragments, preferred tools, stage overrides, and references.
- `SkillBinding`: app-level activation rule that selects a skill for a specific stage with a priority.
- `PlatformSkillRuntime`: resolves bound skills for the current app/stage and injects them into runtime prompts.

## Runtime path

1. Built-in skill bundles are registered at orchestrator startup.
2. Each app manifest binds a subset of skills to one or more stages.
3. When a runtime starts, it resolves stage-matching skills.
4. Resolved skill prompt fragments are appended to the system/context prompt.
5. Preferred tools are exposed as guidance but still pass through normal tool permissions.

## Current built-in skills

- `general_qa`
- `tool_use_hygiene`
- `source_grounding`
- `research_planning`
- `research_synthesis`

## Current integration

- `chat.reply`
  - `general_qa`
  - `tool_use_hygiene`
  - `source_grounding`
- `research.plan`
  - `research_planning`
- `research.summarize`
  - `source_grounding`
  - `research_synthesis`
- `research.report`
  - `source_grounding`
  - `research_synthesis`

## Notes

- Skills are distinct from MCP:
  - MCP provides external capability access.
  - Skills provide domain workflow/instruction overlays.
- Skills are distinct from ToolRegistry:
  - ToolRegistry exposes callable tools.
  - Skills shape how the agent should use available tools and structure work.
