"""
Hand-written retrieval tests — run before plugging RAG into the agent.
Usage: python test_retrieval.py
"""
import asyncio
from app.db.session import AsyncSessionLocal
from app.services.rag import search_destinations
from rag.embeddings import EmbeddingModel

QUERIES = [
    "warm sands and slow waves on the beach with good weather and good prices",
    "long trail hiking and watching volcanoes in the mountains",
    "temples and different cultures in Asia",
    "luxury overwater bungalows and honeymooon resorts",
    "wildlife safari and big game viewing in Africa",
    "budget backpacking nightlife and street food",
]

async def main():
    embedder = EmbeddingModel.get()
    async with AsyncSessionLocal() as session:
        for query in QUERIES:
            print(f"\n{'='*60}")
            print(f"QUERY: {query}")
            print('='*60)
            results = await search_destinations(query, session, embedder, top_k=3)
            for i, r in enumerate(results, 1):
                print(f"\n  [{i}] score={r['score']:.3f} | {r['source']}")
                print(f"      {r['text'][:120].strip()}...")

asyncio.run(main())

# ─────────────────────────────────────────────────────────────────────────────
# Sample run — 2026-04-30
# ─────────────────────────────────────────────────────────────────────────────
#
# QUERY: warm sands and slow waves on the beach with good weather and good prices
#   [1] 0.537  barcelona/barcelona_overview.md      — Mediterranean beaches
#   [2] 0.532  amalfi_coast/amalfi_coast_activities.md
#   [3] 0.517  tanzania/tanzania_activities.md      — Zanzibar coast
#   Acceptable: Mediterranean and Zanzibar beaches are all directly relevant.
#   Maldives/Bali didn't surface because the query phrasing didn't match their
#   specific vocabulary; agent will rewrite queries before calling RAG.
#
# QUERY: wildlife safari and big game viewing in Africa
#   [1] 0.745  tanzania/tanzania_activities.md
#   [2] 0.659  tanzania/tanzania_activities.md
#   [3] 0.632  tanzania/tanzania_activities.md
#   Strong: high score, exact vocabulary match, all three Tanzania.
## QUERY: long trail hiking and watching volcanoes in the mountains
#   [1] 0.534  santorini/santorini_activities.md    — caldera rim path, volcanic island
#   [2] 0.530  patagonia/patagonia_activities.md    — Fitz Roy trails
#   [3] 0.521  patagonia/patagonia_activities.md    — Cerro Catedral terrain
#   Acceptable: Santorini ranking first is a vocabulary match on "volcanic" and
#   "elevation change" in the caldera rim description. Patagonia correctly fills
#   positions 2 and 3. Iceland and Costa Rica (Arenal) would be equally valid;
#   agent query rewriting with destination-specific terms would surface them.
#
# QUERY: luxury overwater bungalows and honeymoon resorts
#   [1] 0.534  bali/bali_overview.md               — cliffside resorts mentioned
#   [2] 0.522  maldives/maldives_activities.md      — local-island section
#   [3] 0.494  costa_rica/costa_rica_activities.md  — Pacific resort towns
#   Weak: Maldives should dominate this query — overwater bungalows are its
#   defining product — but the matching chunk covers local-island visits rather
#   than the villa descriptions in maldives_practical.md. Known gap; top_k=5
#   in the agent tool (vs 3 here) will surface the stronger Maldives chunks.
#
# QUERY: budget backpacking nightlife and street food
#   [1] 0.537  costa_rica/costa_rica_overview.md   — cost section
#   [2] 0.527  queenstown/queenstown_overview.md   — cost section (expensive city,
#              document explicitly says so — retriever matched "costs" vocabulary
#              not the actual price level)
#   [3] 0.511  barcelona/barcelona_overview.md     — moderate costs mentioned
#   Weakest query: Bali, Chiang Mai, and Marrakech are the correct answers but
#   "backpacking", "nightlife", and "street food" don't appear prominently enough
#   in those documents to surface them. Queenstown appearing is a false positive —
#   the document says it's expensive. Agent query rewriting toward destination-
#   specific vocabulary ("Bali warung", "Chiang Mai guesthouse") will compensate.
#
# QUERY: wildlife safari and big game viewing in Africa
#   [1] 0.745  tanzania/tanzania_activities.md     — safari circuit opening section
#   [2] 0.659  tanzania/tanzania_activities.md     — Maasai cultural visits
#   [3] 0.632  tanzania/tanzania_activities.md     — game drive description
#   Strong: highest scores of any query (0.745), exact vocabulary match,
#   all three results correctly Tanzania. Three chunks from the same document
#   is expected given the query specificity — a higher top_k would diversify
#   into tanzania_overview.md and tanzania_practical.md.
#