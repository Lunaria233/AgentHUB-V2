---
name: source_grounding
display_name: Source Grounding
description: Keep answers grounded in retrieved evidence and explain citation discipline.
tags:
  - citations
  - rag
tools:
  - search
---
# Source Grounding

## Instructions
- Prefer claims that can be linked to retrieved evidence.
- Surface uncertainty when evidence is incomplete or conflicting.
- Use citations or source summaries when they increase trust.

## References
- references/grounding-policy.md

## Stage: research.summarize
- Summaries should mention what evidence was found and what remains uncertain.

## Stage: research.report
- Final reports should cite the strongest supporting sources for each major claim.
