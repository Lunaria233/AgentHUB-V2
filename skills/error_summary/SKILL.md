---
name: error_summary
display_name: Error Summary
description: Summarize runtime errors and map them to actionable next states.
tags:
  - software_engineering
  - diagnosis
tools:
  - command_run_tool
  - file_read_tool
---
# Error Summary

## Instructions
- Focus on the most relevant failing stacktrace lines.
- Classify failure into one of: context_missing, patch_bug, env_or_dependency, unknown.
- Propose the next harness action as one of: RETRIEVING, CODING, RUNNING, FAILED.
- Keep diagnosis short and directly useful for routing.

## Stage: se.diagnose
- Produce actionable diagnosis using command, stdout, stderr, traceback, and constraints.

