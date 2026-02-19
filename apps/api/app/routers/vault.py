import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.schemas.common import ApiEnvelope
from app.services.vault_indexer import build_tree, top_level_folders, tree_signature

router = APIRouter(prefix="/vault", tags=["vault"])


@router.get("/tree", response_model=ApiEnvelope[dict])
def vault_tree() -> ApiEnvelope[dict]:
    tree = build_tree(settings.vault_root_path, settings.tree_max_depth)
    return ApiEnvelope(data=tree)


@router.get("/folders", response_model=ApiEnvelope[list[str]])
def vault_folders() -> ApiEnvelope[list[str]]:
    tree = build_tree(settings.vault_root_path, settings.tree_max_depth)
    return ApiEnvelope(data=top_level_folders(tree))


@router.get("/stream")
async def vault_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        previous_signature = ""

        while True:
            if await request.is_disconnected():
                break

            tree = build_tree(settings.vault_root_path, settings.tree_max_depth)
            signature = tree_signature(tree)

            if signature != previous_signature:
                payload = {
                    "signature": signature,
                    "folders": top_level_folders(tree),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                yield f"event: vault_tree\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
                previous_signature = signature

            await asyncio.sleep(settings.vault_watch_interval_sec)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
