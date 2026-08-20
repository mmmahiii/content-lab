---
type: "query"
date: "2026-08-20T15:25:20.449755+00:00"
question: "has everything been mapped"
contributor: "graphify"
outcome: "useful"
source_nodes: ["app/page-workspace.tsx", "services/asset_packs.py"]
---

# Q: has everything been mapped

## Answer

No. Expanded from original query via graph vocab: [app, files, mapped, code, source, packages, document]. The graph fully scanned the supported code corpus under apps: 236 files, about 135,712 words, producing 3,330 nodes and 9,111 graph edges. It does not cover the rest of the repository, including packages, scripts, docs, and artifacts. Mapping is also not perfectly lossless: diagnostics reported dangling endpoints and collapsed same-endpoint relationships.

## Outcome

- Signal: useful

## Source Nodes

- app/page-workspace.tsx
- services/asset_packs.py