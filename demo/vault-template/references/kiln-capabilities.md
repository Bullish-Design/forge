---
title: Kiln Capability Matrix
tags:
  - kiln
  - capabilities
---

# Kiln Capability Matrix

This matrix maps key kiln-facing features to concrete demo artifacts.

| Area | Demonstrated By | Expected Output |
| --- | --- | --- |
| Markdown parsing | `index.md` | Rendered headings/tables/callouts/code/math |
| Wikilinks + backlinks | `index.md`, `projects/forge-v2.md` | Cross-page navigation and backlink sections |
| Tags | Frontmatter and inline tags | Tag index pages in generated output |
| Folder pages | `daily/`, `projects/`, `references/` dirs | Navigable folder listings |
| Attachments | `assets/demo-diagram.svg` embed | Inline asset rendering |
| Watch rebuild loop | Mutation steps in validation script | Output file mtime updates |
| Webhook hook (`--on-rebuild`) | kiln-fork -> `/internal/rebuild` | SSE rebuild event stream |
| Overlay injection | `demo/overlay/ops.js` + `ops.css` | Panel appears on served HTML |
| API proxy | `/api/agent/apply` via overlay | Deterministic JSON response |

See also [[projects/forge-v2]] and [[daily/2026-04-26]].
