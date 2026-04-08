---
name: patch_summary
display_name: Patch Summary
description: Keep code changes minimal, localized, and explainable before execution.
tags:
  - software_engineering
  - coding
tools:
  - patch_write_tool
  - file_read_tool
---
# Patch Summary

## Instructions
- Prefer minimal patch scope that satisfies the current step.
- Explain why each file was changed and what behavior changed.
- Preserve existing interfaces unless task explicitly asks for breaking changes.
- Avoid test file edits unless constraints allow it.

## Stage: se.code
- Before patch generation, summarize intended file-level changes and verification impact.

