---
title: Forge V2 Demo Home
tags:
  - demo
  - kiln
  - forge-overlay
---

# Forge V2 Demo Home

This vault is intentionally designed to exercise real rendering and navigation behavior in the kiln ecosystem.

## Primary Links

- [[projects/forge-v2|Forge V2 Plan]]
- [[references/kiln-capabilities|Kiln Capability Matrix]]
- [[daily/2026-04-26|Daily Demo Log]]
- [[experiments/live-reload|Live Reload Note]]

## Embedded Section

![[projects/forge-v2#Live Demo Checkpoints]]

## Feature Surface

> [!info] Overlay + SSE
> The injected overlay panel should appear on every HTML page and update when rebuild events arrive.

| Capability | Demo Example |
| --- | --- |
| Wikilinks | `[[projects/forge-v2]]` |
| Embeds | `![[projects/forge-v2#Live Demo Checkpoints]]` |
| Tags | `#demo #kiln` |
| Tables | This section |
| Code blocks | Python block below |
| Math | Formula below |
| Tasks | Checklist below |
| Assets | SVG embed below |

```python
from pathlib import Path

root = Path("/demo")
print(f"running from {root}")
```

$$
\text{Rebuild Latency} = \frac{\Delta\text{output mtime}}{\Delta\text{input write}}
$$

- [x] Initial vault render
- [ ] Interactive walkthrough complete
- [ ] Apply/undo cycle validated through overlay proxy

![[assets/demo-diagram.svg]]

Footnote example for markdown parsing support.[^demo-note]

[^demo-note]: This note confirms extended markdown parsing survives the full pipeline.

Inline tags: #demo #integration #forge
