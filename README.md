# Enterprise Agentic Systems v3.1 — Consolidated Monorepo

Built phase-by-phase with agy (Antigravity IDE), verified independently via pytest.

## Phases
| Phase | Module | Tests |
|-------|--------|-------|
| 0 | Core Backbone — WAMMR router, File Memory Engine, Orchestrator (Planner-Builder-Judge), Temporal Event Broker, HITL Gateway | 10 |
| 1 | Secure Sandbox (SES) + Safety Gatekeeper (AISG / NeMo) + Command Audit Logger | 11 |
| 2 | Agent Budget & Telemetry Manager (ABTM) + Webhook & Messaging Gateway (WMG) | 13 |
| 3 | CodexForge — full (extends MVP v2): Goal Router, Context Indexer, Advisor-Editor, REPL, Test Harness, Cloud-Detached Runner, Blueprint Engine | 29* |
| 4 | BrandStream — Ingestion (Astros), Creative Director (Oracle), Parallel Auditing (incl. sim validators) | 13 |
| 5 | BrandStream — Media Synthesis (ComfyUI/Three.js clients, Offloaded Transcode, Skeleton/Re-ID/C2PA filters) | 9 |
| 6 | BrandStream — Speech-to-Speech Voice Gateway (WebSocket, interruption, delegation, UI cards) | 6 |
| 7 | Dashboards — Memory Galaxy (semantic graph) + 3D Office + Orchestration glue | 6 |

*Phase 3 test count is combined with phases 0+1 in its run.

**Total verified: 73 tests passing across all phases.**

## Run tests
```
PYTHONPATH=phase0:phase1:phase2:phase3:phase4:phase5:phase6:phase7 \
  python3 -m pytest --import-mode=importlib phase*/tests/ -q
```

## Notes / honest caveats
- LLM-dependent paths use mock providers offline; real APIs need keys in env.
- Docker/gVisor SES runs as config + logic; gVisor execution validated only on Linux.
- Media (Phase 5) and Voice (Phase 6) are client/stub layers — no local FFmpeg/ComfyUI/audio.
- diffSAE intentionally NOT built (unbuildable); AISG = NeMo semantic scan only.
- Dashboards (Phase 7) are static HTML + CDN Three.js, no build step.

## Source design
- `agentic_systems_v3.1_full.pdf` (the v3.1 architecture doc)
- `agy_agentic_systems_proposal_v3.1.md`
