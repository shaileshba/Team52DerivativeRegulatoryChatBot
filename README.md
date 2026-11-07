# CFTC Regulatory Assistant

A local working pilot based on the supplied scope document, with FastAPI, a responsive web chat, SQLite FTS5 retrieval, original PDF viewing, immutable corpus snapshots, audit records, feedback and Compliance hand-offs.

For a guided walkthrough with presenter notes, sample questions, and evaluation talking points, see [the demo script](DEMO.md).

## Run on Windows

Install Python 3.12+ and uv, then run from this directory:

```powershell
.\start.ps1
```

Open http://127.0.0.1:8000. API documentation is at `/docs`. The initial PDF extraction takes several minutes; later runs reuse the content-addressed snapshot. For manual setup:

```powershell
uv venv --cache-dir .cache/uv
uv pip install --python .venv/Scripts/python.exe --cache-dir .cache/uv -r requirements.lock
.venv/Scripts/python.exe -m app.ingest
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run verification after ingestion with `.venv/Scripts/python.exe -m pytest -q`.

## Reproducible retrieval evaluation

The feedback about a small evaluation with no saved JSON is addressed by a frozen **65-question retrieval dataset**, covering every one of the 13 parts. It has 46 tuning questions and 19 held-out questions (approximately 70/30), with both splits represented in every part. These are provisional author-created section labels, **not an SME-approved golden set**. The repository previously contained six integration tests and no 14-case evaluation file; this benchmark is new.

Run the held-out comparison:

```powershell
.venv/Scripts/python.exe -m app.evaluate
```

Use `--split tuning` for development. Do not change ranking parameters or labels based on held-out scores; use a new independently reviewed held-out set when the old set has influenced development. The committed split assignments in `evaluation/questions.json` are read directly, never randomized by the runner. `evaluation/build_dataset.py` records how the initial dataset was authored; it is not part of an evaluation run.

Four methods run against the same frozen corpus, without part filtering: BM25, citation-first BM25, lexical TF-IDF cosine similarity, and BM25/TF-IDF reciprocal-rank fusion. TF-IDF is a lexical vector baseline, not a neural embedding model. The citation-first baseline is an offline comparator, not an exact replay of the application's retrieval implementation. BM25 uses an isolated in-memory index so superseded snapshots cannot affect its corpus statistics. Results are deduplicated by CFR section before top-five metrics are computed.

Each run creates `eval_runs/<run_id>/results.json`, `corpus.json`, and `questions.json`. The results include:

- A manifest with corpus snapshot, source PDF hashes, frozen input hashes, evaluator hash, Python/SQLite versions, method configuration, split counts, and model/prompt identifiers (none in this extractive evaluation).
- Per-question expected citations, ranked chunk IDs, retrieved citations, scores, PDF pages, Recall@5, MRR@5, Hit@5, and pass/fail. A query passes only when all expected sections appear in the first five unique retrieved sections.
- Aggregate and per-part metrics for the selected split. These are retrieval metrics; they do not establish answer faithfulness, legal applicability, citation support, or production readiness.

The saved corpus allows replay without the live database or PDF ingestion:

```powershell
.venv/Scripts/python.exe -m app.evaluate --replay eval_runs/2026-11-07T062708226565_0000_788da2b98a/results.json
```

Replay verifies the frozen input and evaluator hashes, requires the recorded Python/SQLite runtime and method configuration, and checks every ranking, score, and metric for an exact match. Install the pinned `requirements.lock` to recreate the environment. Keep all three JSON files together when sharing a run. Evaluation runs remain in the repository rather than the ignored runtime `data` directory.

Initial held-out results on corpus snapshot `928303ab332c82991901`:

| Retrieval method | Recall@5 | MRR@5 | Questions |
| --- | ---: | ---: | ---: |
| BM25 | 94.74% | 0.711 | 19 |
| Citation-first BM25 | 94.74% | 0.737 | 19 |
| Lexical TF-IDF | 84.21% | 0.645 | 19 |
| BM25 + TF-IDF fusion | 94.74% | 0.747 | 19 |

Fusion has the highest observed MRR, but it does not improve Recall@5 over BM25 on this small set. No production method was selected or changed based on these results. The questions are based largely on headings and include overlapping source sections across splits, so these scores may overestimate generalization. Obtain independent SME labels, a larger and more varied held-out set, and approved neural embedding/reranking baselines before using this evaluation for a release decision.

## Implemented behavior

Only the 13 individual Part PDFs in `RAGData` are indexed. The scope document, complete volumes and Dodd–Frank Act are excluded to avoid mixing requirements, duplicate passages and out-of-scope content into answers. Sections retain their heading, source filename, PDF page and snapshot hash. Candidate builds commit atomically only after all 13 parts have nonempty content. Old snapshots remain available for audit and citation replay. Replacing a PDF creates another snapshot on the next ingestion run.

Classification occurs before retrieval. Common case-specific, enforcement and breach requests are routed to Compliance; other named regulators are refused. Historical comparisons are deferred because only a single source vintage is provided. Identifier patterns block common account, email and LEI inputs; blocked questions are redacted in persistent logs. These deterministic heuristics are a pilot control, not comprehensive entity detection.

Exact section lookup takes priority over FTS5 keyword search. Local mode returns verbatim stored excerpts, never generated legal claims or invented summaries. Citations resolve to immutable local records and the PDF page where the section starts. This is section-level extraction, not paragraph-level legal parsing. Keyword results are candidates, not calibrated confidence estimates. The UI labels them as source excerpts.

Audit records pin returned sources, corpus snapshot, pipeline version and the absence of an LLM. Feedback links to answers. Hand-offs are saved locally and can be copied to an approved Compliance channel; the application does not transmit them. Data is stored in `data/corpus.sqlite`; protect that directory and establish retention before organizational use.

## Production gaps and release gates

This is not the validated production system described in the scope. It intentionally binds to localhost. Do not expose the service on a network: there is no SSO, authorization, rate limiting, encrypted audit storage, or retention automation. The provided 2025 sources do not establish current law or effective dates.

Before a firm pilot: obtain Compliance corpus approval and the 300-question SME golden set; implement the stratified held-out evaluation and release gates; reconcile extracted sections to an authoritative TOC; validate extraction and applicability; add comprehensive PII detection and approved escalation routing; configure SSO/RBAC, protected logs and retention. The local candidate activation check is structural only, not the required production blue/green release gate.

The proposed cloud stack remains integration work: approved Bedrock generation/classification/embeddings, OpenSearch hybrid retrieval, reranking, S3/Postgres storage, Langfuse tracing, Airflow refresh jobs, eCFR point-in-time ingest, Federal Register preambles, FAQs, definition/cross-reference enrichment, and paragraph anchors. No cloud credentials or approved infrastructure were supplied, and no external model is contacted. Plain-language synthesis must preserve claim-to-source validation before it can replace local extractive output. All production model, corpus and prompt changes require the evaluation and governance approvals in the supplied scope.
