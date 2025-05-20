# services/file_handler.py
import httpx, uuid, os, logging

async def download_teams_file(content_url: str, bearer_token: str,
                              dst_dir: str = "/tmp") -> str:
    filename  = f"teams_policy_{uuid.uuid4()}.pdf"
    dst_path  = os.path.join(dst_dir, filename)

    async with httpx.AsyncClient() as client:
        r = await client.get(content_url,
                             headers={"Authorization": f"Bearer {bearer_token}"})
        r.raise_for_status()
        with open(dst_path, "wb") as f:
            f.write(r.content)

    logging.info(f"📥  Saved Teams attachment → {dst_path}")
    return dst_path
