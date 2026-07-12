# Phase 4 — BrandStream AI: Ingestion + Creative Director + Parallel Auditing

Phase 4 implements the ingestion, creative copy generation, localization, and parallel auditing layer of BrandStream AI, fully wired into the Phase 0-3 core components (`ModelRouter`, `MemoryEngine`, `GuardrailChecker` (`AISG`), `BudgetManager` (`ABTM`), and `WebhookMessagingGateway` (`WMG`)).

## Component Layout

- **Ingestion Manager "Astros"** (`brandstream/ingestion/`):
  - `scraper.py`: Fetches target URLs and compiles findings to clean Obsidian Markdown, saved directly to `MemoryEngine`-backed workspaces.
  - `reviewer.py`: Auxiliary Multimodal LLM (MLM) Semantic Reviewer that prunes low-quality metadata, verifies spatial layout tags, and cleans scraping databases.
  - `catalog.py`: Structured Catalog Ingestor parsing PDFs/CSVs/Excel files to automatically identify underserved location targets.
- **Creative Director "Oracle"** (`brandstream/creative/`):
  - `oracle.py`: Copywriter & script compiler that enforces brand **Voice Guide** (banned terms, tone compliance) and checks for factual deviations against source research. Includes:
    - `VisualBlueprintAnalyzer`: Extracts spatial layout specifications (ratios, coordinates) from styling references.
    - `DynamicLocalization`: Automatically translates promotional script copy to N target locales.
- **Parallel Auditing Sub-agents** (`brandstream/audit/`):
  - `auditor.py`: Consists of validation engines to verify correctness before rendering assets:
    - `CopyAuditor`: Audits scripts and storyboard structures for length, frames, and stylistic compliance.
    - `ChessValidator`: Integrates `python-chess` verification (with rule-based fallback if library not installed) to catch illegal moves or state inconsistencies.
    - `LogicStateValidator`: Validates coordinates ordering/boundaries inside visual blueprints and frame sequencing inside storyboards.

---

## Directory Listing
```
phase4/
├── conftest.py
├── README.md
├── brandstream/
│   ├── __init__.py
│   ├── brandstream_core.py (Coordinates the full pipeline)
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── scraper.py
│   │   ├── reviewer.py
│   │   ├── catalog.py
│   ├── creative/
│   │   ├── __init__.py
│   │   ├── oracle.py
│   └── audit/
│       ├── __init__.py
│       └── auditor.py
└── tests/
    ├── __init__.py
    ├── test_astros.py
    ├── test_oracle.py
    ├── test_audit.py
    ├── test_localization.py
    └── test_wiring.py
```

---

## Test Execution Summary

All 13 offline tests run successfully:

```bash
============================== 13 passed in 0.03s ==============================
```

- **Astros**: Mock scrapes competitor content, runs MLM semantic reviewing filtering short/generic tags, and parses CSV/PDF/Excel catalogs to identify underserved targets.
- **Oracle**: Rejects copy violating brand Voice Guide config (e.g. banned keywords), accepts clean copy, checks factual deviations, and drafts scripts.
- **Audit**: `ChessValidator` verifies moves, catching turn alternation violations or duplicate square occupancy; `LogicStateValidator` validates coordinates bounding box bounds [0.0, 1.0].
- **Localization**: Produces correct translated strings/mocks for given locales.
- **Wiring**: Full integrated pipeline test validating interaction with `ModelRouter`, `BudgetManager` (usage tracing), `GuardrailChecker` (safety rules), and `WebhookMessagingGateway`.

---

## What Phase 5 Consumes

Phase 5 (Multi-modal Video Synthesizer & Rendering Sandbox) consumes the output of Phase 4:
1. **Factual, Validated Scripts (`narration`)**: Narration texts checked for voice guide compliance and factual alignment with competitor research.
2. **Storyboard Sequence (`storyboard`)**: An array of sequentially numbered frames matching (`frame`, `visual_prompt`, `audio_script`).
3. **Visual Blueprint Specs (`visual_blueprint`)**:
   - `layout`: Layout style tags (e.g., `split-screen`, `grid`).
   - `aspect_ratio`: Targeting dimension ratios (e.g., `16:9`, `9:16`).
   - `coordinates`: Exact bounding box coords `[x1, y1, x2, y2]` for text overlays, graphics, or actor skeleton anchoring.
   - `weathering`: Aesthetic styles (e.g., `rust`, `clean`).
4. **Localized Copy Variants (`localized_variants`)**: Translation dictionaries (`locale` -> `translated_narration`) to drive localized audio synthesis pipelines (e.g., ElevenLabs).
