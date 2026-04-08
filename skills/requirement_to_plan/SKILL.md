---
name: requirement_to_plan
display_name: Requirement To Plan
description: Convert natural-language coding requirements into structured engineering plans.
tags:
  - software_engineering
  - planning
tools:
  - repo_search_tool
  - file_read_tool
---
# Requirement To Plan

## Instructions
- Convert user task into a concrete engineering objective and explicit constraints.
- Extract target modules/files before proposing edits.
- Define verification strategy with an executable command.
- Keep plan steps atomic so they can be observed in harness iterations.

## Stage: se.plan
- Return compact plan with goal, modules, constraints, verify command, and ordered steps.

