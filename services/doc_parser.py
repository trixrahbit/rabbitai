# services/doc_parser.py
"""
Minimal PDF-→OpenAI→JSON extractor + DB persister
Fits your existing env vars (openai.api_* already set elsewhere).
"""

import json, logging, uuid, pdfplumber, os
from datetime import datetime
from typing import List, Dict

from azure_openai import query_openai, secondary_query_openai
from config    import get_db_connection     # <-- you already have this

# ----------------------------- TEXT EXTRACTION ------------------------------
def _extract_text(path: str) -> str:
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def _chunk(text: str, max_len: int = 6000) -> List[str]:
    """
    Azure GPT-4o has an 8k token limit; quick char-based chunker is enough
    for typical 20-30 page policies.
    """
    parts, buf = [], ""
    for line in text.splitlines():
        if len(buf) + len(line) > max_len:
            parts.append(buf)
            buf = ""
        buf += line + "\n"
    if buf:
        parts.append(buf)
    return parts

# ----------------------------- OPENAI CALL ----------------------------------
SYSTEM_PROMPT = (
    "You are an insurance-policy compliance assistant.\n"
    "Return ONLY valid JSON: a list of objects, "
    "each having keys 'requirement' and optional 'category'."
)

async def extract_requirements(pdf_path: str) -> List[Dict[str, str]]:
    text   = _extract_text(pdf_path)
    chunks = _chunk(text)

    reqs: List[Dict[str, str]] = []
    for chunk in chunks:
        resp = await secondary_query_openai(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": chunk},
            ],
            max_tokens=800,
            temperature=0,
        )
        try:
            reqs.extend(json.loads(resp))
        except json.JSONDecodeError as e:
            logging.error(f"❌ JSON parse error in chunk: {e}\n{resp[:400]}")
    return reqs

# ----------------------------- DB PERSIST -----------------------------------
async def persist(policy_id: str, reqs: List[Dict[str, str]]):
    """
    Stores each requirement row in a table called PolicyRequirements.
    Uses your existing async `get_db_connection()`, not SQLAlchemy ORM.
    """
    if not reqs:
        return 0

    insert_sql = """
        INSERT INTO PolicyRequirements
        (policyId, requirementText, category, createdUtc)
        VALUES (:policyId, :req, :cat, :now)
    """

    async with get_db_connection() as conn:
        async with conn.begin():
            for r in reqs:
                await conn.execute(
                    insert_sql,
                    {
                        "policyId": policy_id,
                        "req":      r.get("requirement"),
                        "cat":      r.get("category", "general"),
                        "now":      datetime.utcnow(),
                    },
                )
    return len(reqs)
