# services/policy_ingestion.py  (CREATE if you don't have it)

import uuid, os, logging
from datetime import datetime
from services.doc_parser import extract_requirements, persist
from config import get_db_connection   # reuse your helper

PDF_STORE = "/var/tmp/policies"        # adjust as desired
os.makedirs(PDF_STORE, exist_ok=True)

async def ingest_policy(local_path: str, tenant_id: int = 1) -> int:
    """
    1. Moves PDF to permanent storage folder
    2. Inserts a row in Policies table
    3. Parses & stores requirements
    4. Returns requirement count
    """
    policy_id = str(uuid.uuid4())                      # GUID for cross-tables
    final_path = os.path.join(PDF_STORE, f"{policy_id}.pdf")
    os.rename(local_path, final_path)                  # move/rename

    # --- store minimal metadata in a Policies table -------------------------
    insert_sql = """
        INSERT INTO Policies (id, tenantId, filename, uploadedUtc)
        VALUES (:id, :tenantId, :filename, :ts)
    """
    async with get_db_connection() as conn:
        async with conn.begin():
            await conn.execute(
                insert_sql,
                {
                    "id": policy_id,
                    "tenantId": tenant_id,
                    "filename": os.path.basename(final_path),
                    "ts": datetime.utcnow(),
                },
            )

    # --- parse & persist requirements ---------------------------------------
    reqs = await extract_requirements(final_path)
    await persist(policy_id, reqs)

    logging.info(f"✅ Policy {policy_id}: stored {len(reqs)} requirements.")
    return len(reqs)
