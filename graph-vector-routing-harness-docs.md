# RAG-vs-GraphRAG Architecture Advisor

## 1. Overview

An automated diagnostic tool that ingests any company's raw corpus and determines, without human labeling or manual dataset selection, whether their data justifies building a **Graph RAG** pipeline, is better served by **plain vector RAG**, or needs a **hybrid** approach — output as a single recommendation backed by measurable evidence.

**Core question the project answers:** Given an arbitrary dataset, can the system automatically determine — with no manual query labeling, no manual schema design, no human judgment call — whether that data has enough relational structure to justify the cost of building and maintaining a knowledge graph, versus just using vector search?

**Why this framing over a live per-query router:** a live router (deciding graph vs. vector per query, in production) requires a company to have *already* built both a graph and a vector index. This tool answers the earlier, higher-value question — *should they build the graph at all* — which is where most companies are actually stuck. The routing logic from that design isn't discarded; it becomes the evidence-generation mechanism behind the recommendation (see §4.4).

---

## 2. Architecture

```
                    Company's raw corpus (any domain, any format)
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   ER Extraction Pipeline           │
                    │  Raw corpus → GLiNER-Relex          │
                    │  (joint entity+relation) →           │
                    │  Entity Resolution                   │
                    └───────────────┬────────────────────┘
                                     │
                     ┌───────────────┴────────────────┐
                     ▼                                  ▼
             ┌──────────────┐                  ┌────────────────┐
             │    Neo4j      │                  │  FAISS/Chroma    │
             │  (graph DB)   │                  │  (vector store)   │
             └──────┬───────┘                  └────────┬─────────┘
                    │                                     │
                    ▼                                     │
      ┌─────────────────────────┐                        │
      │  Graph Structure Analysis │                        │
      │  density, node degree,     │                        │
      │  connected components      │                        │
      └────────────┬─────────────┘                        │
                    │                                       │
                    ▼                                       ▼
      ┌───────────────────────────────────────────────────────┐
      │              Query Synthesis (LLM, automatic)            │
      │   multi-hop queries from real relation chains +           │
      │   single-hop queries from entity text                      │
      └───────────────────────────┬───────────────────────────┘
                                   │
                                   ▼
      ┌───────────────────────────────────────────────────────┐
      │        Comparative Eval — runs synthesized queries        │
      │   through graph_query (MCP) AND vector_search (MCP)        │
      │   → routing/answer-quality evidence per query               │
      └───────────────────────────┬───────────────────────────┘
                                   │
                                   ▼
      ┌───────────────────────────────────────────────────────┐
      │              Recommendation Engine                        │
      │   combines structural metrics + comparative eval results   │
      │   → RAG-only / GraphRAG-only / Hybrid + supporting evidence │
      └───────────────────────────────────────────────────────┘
                                   │
                                   ▼
                     FastAPI `/analyze` → Diagnostic Report

              All services containerized and deployed on Kubernetes
```

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| ER extraction | GLiNER-Relex | Joint zero-shot entity + relation extraction in one model — makes ingestion data-agnostic (no per-dataset schema/retraining) and avoids error propagation from a two-stage NER→RE pipeline |
| Retrieval backends | Neo4j, FAISS/Chroma | Graph storage + traversal; dense vector storage + search |
| Tool interface | MCP (Model Context Protocol) | Exposes `graph_query` and `vector_search` as discoverable tools used internally by the comparative eval to generate recommendation evidence |
| Service layer | FastAPI | Wraps the pipeline as HTTP endpoints (`/ingest`, `/analyze`); a company points the tool at their corpus and gets a diagnostic report back |
| Orchestration | Kubernetes | Deploys FastAPI service, Neo4j, vector store, and the extraction worker as separate pods/services; demonstrates service discovery and independent scaling of the compute-heavy extraction stage |
| Automation / reporting | n8n (optional) | Re-runs `/analyze` on new-data-arrival or a schedule, posts the diagnostic report to Slack/email |

---

## 4. Component Details

### 4.1 Data-Agnostic Ingestion (ER Extraction Pipeline)

The project accepts **any raw text corpus** (PDFs, articles, structured JSON, CSV rows) — no per-dataset parser or manually-written schema/adapter is required. The ER (entity-relationship) layer is discovered automatically at ingestion time, not hardcoded.

**Pipeline:**
```
Raw corpus (any domain)
   → Generic format reader (PDF/CSV/text extraction — format-level only, not domain-level)
   → GLiNER-Relex: joint zero-shot entity + relation extraction (labels passed per-run, no retraining)
   → Entity Resolution (dedupe/merge same real-world entity across mentions)
   → Neo4j (graph)   +   Vector store (same extracted entity/chunk text, embedded)
```

**Why a joint model instead of two separate stages:**
- **GLiNER-Relex** — a unified architecture in the GLiNER family that performs entity recognition and relation extraction jointly, in a single encoder/forward pass, rather than as two separate models. Both entity and relation types are still specified as arbitrary labels at inference time — zero-shot, no retraining per dataset, same data-agnostic property as before.
- This directly removes the two-stage error-propagation problem: with separate GLiNER (entities) → GLiREL (relations) models, a missed or mislabeled entity span silently breaks any relation extraction depending on it. A joint model shares representations across both tasks in one pass, so entity and relation predictions inform each other instead of relation extraction being strictly downstream of (and blocked by) NER mistakes.
- Practically: one model call per chunk returns both entities and relation triplets together, instead of orchestrating two model calls with an intermediate hand-off.

**Entity Resolution** is a first-class step, not an afterthought: the same real-world entity often surfaces differently across mentions/documents ("J. Smith" vs. "John Smith," slightly different org names). Resolution (embedding similarity + LLM disambiguation) merges these before graph insertion — a genuinely hard ER problem worth calling out explicitly as a project component.

**Automatic query-set generation:** because entity/relation types are discovered per-corpus rather than predefined, hand-labeling "relational vs. semantic" queries per dataset doesn't scale either. An LLM inspects the extracted graph structure and synthesizes multi-hop queries (using real discovered relation chains) and single-hop queries (using entity text) — so the labeled eval set regenerates automatically for any new corpus dropped into the pipeline, keeping the whole harness dataset-agnostic end to end.

**Example query patterns** (illustrated here using a citation-graph-style corpus, but structurally the same for any domain since types are discovered, not predefined):

*Relational / multi-hop (requires graph traversal):*
- "Which papers cite work that this paper's authors also cited?" — 2-hop: paper → references → papers citing those references
- "Who are the co-authors of researchers that cite Paper X?" — citation → author → co-author edges
- "Find papers that bridge two research areas — cited by papers in NLP and also cited by papers in RL" — intersection across citation paths
- "What's the citation path between Paper A and Paper B?" — shortest-path traversal, graph-only capability
- "Which authors have co-authored with someone who later cited their own earlier paper?" — self-citation-via-collaborator pattern
- "List papers published after 2020 that cite at least 3 papers from before 2015 in this subfield" — temporal + structural filter combined

*Semantic / single-hop (vector search suffices):*
- "What is Paper X about?" — abstract lookup
- "Find papers about transformer efficiency techniques" — semantic similarity over abstracts
- "Summarize the main contribution of Paper Y" — single-document retrieval + generation
- "Which papers discuss catastrophic forgetting in continual learning?" — topic-based semantic match, no relational reasoning needed

This split is objectively labelable: relational answers are only derivable by walking edges, so routing correctness can be checked against graph structure itself. A semantic query routed to the graph is a directly measurable misrouting cost (wasted traversal, no accuracy gain) — exactly the kind of data point the eval table should surface.

### 4.2 Graph Structure Analysis (new automatic signal)

Computed directly from the extracted graph, with no manual input:

| Metric | What it indicates |
|---|---|
| Relation density (edges / entities) | Low density → data is mostly independent facts → favors plain RAG |
| Avg. node degree | High-degree hub entities → strong relational structure → favors GraphRAG |
| % entities with 2+ relations | Low % → data doesn't naturally interconnect → favors plain RAG |
| Connected component structure | One large connected graph → rich traversal potential; many disconnected islands → limited GraphRAG value |
| Relation-type diversity (from GLiNER-Relex) | More distinct relation types → richer possible multi-hop questions |

These metrics are the **objective, data-only** half of the recommendation — they don't require running any queries, just analyzing the graph GLiNER-Relex already built.

### 4.3 Query Synthesis + Comparative Eval (the router logic, repurposed as evidence)

The routing/query-classification work is still built — but its role changes from "live production router" to **"the mechanism that generates comparative evidence for the recommendation."**

1. **Query synthesis** — an LLM inspects the extracted graph and generates a representative query set: multi-hop queries from real discovered relation chains, single-hop queries from entity text (same mechanism as before, still fully automatic per corpus).
2. **Comparative eval** — every synthesized query is run through *both* `graph_query` and `vector_search` (MCP tools), and answer quality is scored for each. Where graph-based answers are meaningfully better, that's evidence the corpus needs GraphRAG; where they're equivalent, that's evidence plain RAG suffices.
3. This produces the **empirical, query-driven** half of the recommendation — complementing the structural metrics in §4.2 with an actual quality comparison, not just graph shape.

The three query-classification approaches from earlier design work (heuristic / LLM-based / fine-tuned) now serve as three ways of *predicting* which retrieval strategy a query needs — useful as an internal consistency check (does the corpus's synthesized query mix actually split the way the structural metrics suggest?) rather than as a deployed production component.

### 4.4 Recommendation Engine

Combines §4.2 and §4.3 into a single output:

```
Recommendation: GraphRAG | RAG-only | Hybrid
Confidence: <derived from agreement between structural + empirical signals>
Evidence:
  - Relation density: 0.34 edges/entity
  - X% of synthesized queries showed graph_query outperforming vector_search
  - Y% of entities have 2+ relations
  - Largest connected component covers Z% of extracted entities
```

If structural metrics and comparative eval results disagree (e.g., dense graph but graph retrieval doesn't actually improve answers), that disagreement itself is a useful, reportable finding — it means the data *looks* relational but the relations aren't the kind that help answer real questions, which is a genuinely interesting thing for a diagnostic tool to surface.

### 4.5 MCP Tool Layer
- `graph_query(cypher_or_nl_query)` → returns subgraph / traversal result
- `vector_search(query, k)` → returns top-k chunks
- Used internally by the comparative eval (§4.3), not exposed as a live production routing path in this version of the project.

### 4.6 FastAPI Service
| Endpoint | Method | Description |
|---|---|---|
| `/ingest` | POST | Accepts a raw corpus (upload or path), triggers the ER extraction pipeline |
| `/analyze` | POST | Runs structure analysis + query synthesis + comparative eval, returns the full diagnostic report |
| `/status/{job_id}` | GET | Polls progress for long-running ingestion/analysis jobs |

### 4.7 Kubernetes Deployment
- Separate pods: `fastapi-service`, `neo4j`, `vector-store`, `extraction-worker` (GLiNER-Relex, likely GPU-beneficial and worth isolating for independent scaling)
- Internal service discovery between the API and both retrieval backends
- Optional: HPA on the extraction worker specifically, since ingestion is the most compute-heavy stage and the one most likely to need to scale with corpus size

### 4.8 n8n Automation (optional)
- Trigger `/analyze` on a schedule or on new-data-arrival, useful for companies whose corpus grows over time and want to re-check whether their recommendation has changed
- Post the diagnostic report summary to Slack/email

---

## 5. Evaluation Methodology

*Note: this section evaluates the diagnostic tool's own accuracy — i.e., "does the recommendation it gives actually hold up?" — using the internal query-classification approaches (§4.3) as a consistency check, not as a deployed router.*

### 5.1 Synthesized Query Set
- Generated automatically per corpus (see §4.1/§4.3) — an LLM inspects the extracted graph structure and synthesizes ~50–100 queries, split into:
  - **Relational / multi-hop** — requires graph traversal (constructed from real discovered relation chains, e.g., "who co-authored papers with X's advisor?")
  - **Semantic / single-hop** — requires lookup only (constructed from entity text, e.g., "what is paper Y about?")
- A small manual spot-check pass is still recommended before treating the generated set as ground truth, since synthesis quality depends on extraction quality upstream.

### 5.2 Metrics
| Metric | What it measures |
|---|---|
| Classification consistency | Do the three internal query-classification approaches (heuristic/LLM/classifier, §4.3) agree with each other on the synthesized set — a sanity check that the "relational vs. semantic" split is well-defined for this corpus |
| Answer-quality delta | For each synthesized query, how much better/worse is the graph-based answer vs. the vector-based answer — the core evidence feeding the recommendation |
| Structural-empirical agreement | Does the recommendation engine's structural signal (§4.2) agree with its empirical signal (§4.3) — disagreement is itself a reportable finding (§4.4) |
| End-to-end runtime | Time from raw corpus in to diagnostic report out — matters since this is meant to be a practical tool, not just a one-off research script |

### 5.3 Validation Approach
Since there's no single "ground truth" recommendation to check against for an arbitrary company corpus, validation instead relies on:
- **Known-answer test corpora** — one deliberately low-relational corpus (e.g., independent product FAQs) and one deliberately high-relational corpus (e.g., an org chart + citation-style dataset), where the "correct" recommendation is knowable in advance, used to confirm the tool doesn't misclassify obvious cases in either direction
- **Cross-corpus consistency** — running the same corpus twice should produce the same recommendation (checks that GLiNER-Relex extraction and query synthesis aren't introducing unacceptable run-to-run variance)

---

## 6. Project Roadmap

1. Build the ER extraction pipeline: generic format readers → GLiNER-Relex (joint entity + relation extraction) → entity resolution
2. Validate extraction on one small test corpus; tune entity/relation label sets
3. Auto-populate Neo4j + vector store from the same extraction pass
4. Build MCP tool wrappers for both retrieval backends (`graph_query`, `vector_search`)
5. Implement graph structure analysis module (§4.2) — density, degree, connected components, relation-type diversity
6. Build automatic query synthesis (multi-hop/single-hop from discovered graph structure)
7. Build comparative eval — synthesized queries run through both retrieval paths, scored
8. Build the recommendation engine combining structural + empirical signals into a single report
9. Wrap in FastAPI (`/ingest`, `/analyze`, `/status`)
10. Containerize and deploy on Kubernetes
11. Validate against known-answer test corpora (§5.3) — one low-relational, one high-relational — confirm correct recommendations in both directions
12. Validate data-agnosticism: run the full pipeline on a third, unrelated corpus with zero code changes
13. (Optional) Wire n8n for scheduled re-analysis + reporting

---

## 7. Open Questions / Next Steps
- Which two known-answer corpora to use for validation (§5.3) — need one clearly low-relational and one clearly high-relational case
- How to weight structural vs. empirical signals when they disagree in the recommendation engine (§4.4) — simple average, or does one signal override the other in certain cases
- Whether "Hybrid" needs its own threshold logic or falls out naturally as "neither signal is strongly one-sided"
- How much manual QA is needed on GLiNER-Relex's extraction output before trusting it to populate the graph without review
- Whether GLiNER-Relex's joint architecture needs fine-tuning on a sample of representative corpora to hit acceptable accuracy, or works well enough zero-shot out of the box
- Whether the diagnostic report should include a rough cost/complexity estimate for building the recommended pipeline, or stay scoped to "which architecture fits your data"
