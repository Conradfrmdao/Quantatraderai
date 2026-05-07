"""RAG (Retrieval-Augmented Generation) trade memory via pgvector.

Every decision + outcome is stored as an embedding. Before each LLM call,
the top-5 most similar past decisions are retrieved and injected into context.
When a position closes, the realised PnL updates the quality score of the
original decision — positive PnL reinforces, negative PnL reduces.

Requirements:
    1. Enable pgvector extension in Supabase:
       CREATE EXTENSION IF NOT EXISTS vector;

    2. Run migration 20250424000003 (see prisma/migrations/).

    3. Set env:
       OPENAI_API_KEY  — for text-embedding-3-small (cheap, $0.02/1M tokens)
       DATABASE_URL    — already set

If OPENAI_API_KEY is not set, embeddings fall back to a local hash-based
fingerprint (no semantic similarity, but doesn't break anything).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger("quantatraderai.memory.rag")

_EMBED_DIM = 1536   # text-embedding-3-small
_TOP_K     = 5


async def _embed(text: str) -> list[float]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Deterministic hash fingerprint fallback (no semantic meaning,
        # but allows the pipeline to run without OpenAI).
        digest = hashlib.sha512(text.encode()).digest()
        vec = [(b / 127.5 - 1.0) for b in digest[:_EMBED_DIM // 4]]
        vec = vec * (_EMBED_DIM // len(vec))
        vec = vec[:_EMBED_DIM]
        return vec
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "text-embedding-3-small", "input": text[:8000]},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        logger.warning("Embedding failed: %s — using hash fallback", e)
        return await _embed(text)


async def store_decision(
    user_id: str,
    asset: str,
    action: str,
    context_summary: str,
    rationale: str,
    decision_id: str | None = None,
) -> str | None:
    """Embed and store a trading decision. Returns the inserted row ID."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        text    = f"Asset: {asset} Action: {action}\nContext: {context_summary}\nRationale: {rationale}"
        vector  = await _embed(text)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
        import asyncpg, uuid
        conn = await asyncpg.connect(db_url, timeout=8)
        try:
            row_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO "DecisionEmbedding"
                    ("id","userId","asset","action","contextSummary","rationale","embedding","qualityScore","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,NOW())
                """,
                row_id, user_id, asset, action, context_summary[:500], rationale[:500], vec_str, 0.5,
            )
            return row_id
        finally:
            await conn.close()
    except Exception as e:
        logger.warning("store_decision failed: %s", e)
        return None


async def retrieve_similar(
    context_summary: str,
    user_id: str,
    asset: str | None = None,
    top_k: int = _TOP_K,
) -> list[dict[str, Any]]:
    """Return top_k most similar past decisions, weighted by quality score."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return []
    try:
        vector  = await _embed(context_summary)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
        import asyncpg
        conn = await asyncpg.connect(db_url, timeout=8)
        try:
            where = '"userId"=$1'
            args: list = [user_id, vec_str, top_k]
            if asset:
                where += ' AND "asset"=$4'
                args.append(asset)
            rows = await conn.fetch(
                f"""
                SELECT "id","asset","action","rationale","qualityScore","createdAt",
                       1 - ("embedding" <=> $2::vector) AS similarity
                FROM "DecisionEmbedding"
                WHERE {where}
                ORDER BY "qualityScore" * (1 - ("embedding" <=> $2::vector)) DESC
                LIMIT $3
                """,
                *args,
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    except Exception as e:
        logger.warning("retrieve_similar failed: %s", e)
        return []


async def update_quality(decision_id: str, pnl: float, initial_alloc: float) -> None:
    """Adjust quality score based on realised PnL after position close."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return
    if initial_alloc <= 0:
        return
    pnl_pct   = pnl / initial_alloc
    delta     = pnl_pct * 0.1              # gentle update ±10% of PnL %
    new_score = f'"qualityScore" + {delta:.6f}'
    clamp     = 'GREATEST(0.0, LEAST(1.0, '
    try:
        import asyncpg
        conn = await asyncpg.connect(os.getenv("DATABASE_URL"), timeout=8)
        try:
            await conn.execute(
                f'UPDATE "DecisionEmbedding" SET "qualityScore"={clamp}{new_score})) WHERE "id"=$1',
                decision_id,
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.warning("update_quality failed: %s", e)


def format_rag_context(similar: list[dict[str, Any]]) -> str:
    """Format retrieved memories for injection into LLM context."""
    if not similar:
        return ""
    lines = ["=== RELEVANT PAST DECISIONS (learn from these) ==="]
    for s in similar:
        pct   = f"{s.get('similarity', 0):.1%}"
        score = f"{s.get('qualityScore', 0.5):.2f}"
        lines.append(
            f"[{s['asset']} {s['action'].upper()} | sim={pct} quality={score}] {s['rationale']}"
        )
    return "\n".join(lines)
