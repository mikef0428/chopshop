"""Source ingestion endpoints."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from ..config import load as load_settings
from ..db import store
from ..pipeline import ffmpeg, ingest
from ..pipeline.reframe import facecam
from .schemas import (
    MomentsIn,
    MomentsOut,
    SourceOut,
    StreamLayoutIO,
    StreamLayoutOut,
    YouTubeIngestIn,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])

#: Uploads stream to disk in chunks rather than being buffered whole — source
#: videos routinely exceed available RAM.
UPLOAD_CHUNK = 4 * 1024 * 1024


@router.get("", response_model=list[SourceOut])
async def list_sources(limit: int = 50) -> list[SourceOut]:
    sources = await asyncio.to_thread(store.list_sources, limit)
    return [SourceOut.of(s) for s in sources]


@router.get("/{source_id}", response_model=SourceOut)
async def get_source(source_id: str) -> SourceOut:
    source = await asyncio.to_thread(store.get_source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return SourceOut.of(source)


def _youtube_settings(url: str, cookies_from_browser: str | None):
    # Twitch channel links pass through so ingest can explain what to paste instead.
    if not (ingest.is_supported_url(url) or ingest.is_twitch_url(url)):
        raise HTTPException(status_code=400, detail="That is not a YouTube or Twitch URL.")
    settings = load_settings().ingest
    if cookies_from_browser is not None:
        settings = settings.model_copy(update={"cookies_from_browser": cookies_from_browser})
    return settings


async def _source_or_404(source_id: str):
    source = await asyncio.to_thread(store.get_source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return source


def _layout_out(source, layout: facecam.StreamLayout | None) -> StreamLayoutOut:
    return StreamLayoutOut(
        layout=StreamLayoutIO(**asdict(layout)) if layout else None,
        width=source.width or 1920,
        height=source.height or 1080,
    )


@router.get("/{source_id}/stream-layout", response_model=StreamLayoutOut)
async def get_stream_layout(source_id: str) -> StreamLayoutOut:
    """The saved streamer/gameplay boxes for this source, if any."""
    source = await _source_or_404(source_id)
    return _layout_out(source, facecam.load_layout(Path(source.path).parent))


@router.post("/{source_id}/stream-layout/detect", response_model=StreamLayoutOut)
async def detect_stream_layout(source_id: str) -> StreamLayoutOut:
    """Find the streamer's camera automatically and save it (replacing any saved boxes)."""
    from .clips import stream_layout_for

    source = await _source_or_404(source_id)
    (Path(source.path).parent / facecam.LAYOUT_FILE).unlink(missing_ok=True)
    return _layout_out(source, await asyncio.to_thread(stream_layout_for, source))


@router.put("/{source_id}/stream-layout", response_model=StreamLayoutOut)
async def save_stream_layout(source_id: str, payload: StreamLayoutIO) -> StreamLayoutOut:
    """Save boxes the user drew."""
    source = await _source_or_404(source_id)
    width, height = source.width or 1920, source.height or 1080
    for box in (payload.cam, payload.game):
        if box.x + box.w > width or box.y + box.h > height:
            raise HTTPException(status_code=400, detail="A box runs off the edge of the video.")
    layout = facecam.StreamLayout(
        facecam.Box(**payload.cam.model_dump()), facecam.Box(**payload.game.model_dump()), "drawn"
    )
    facecam.save_layout(Path(source.path).parent, layout)
    return _layout_out(source, layout)


@router.get("/{source_id}/frame")
async def source_frame(source_id: str, t: float = 0.0) -> Response:
    """One full-resolution frame as JPEG, to draw the stream layout boxes on."""
    source = await _source_or_404(source_id)
    command = [
        ffmpeg.ffmpeg_path(), "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", source.path,
        "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "pipe:1",
    ]  # fmt: skip
    result = await asyncio.to_thread(subprocess.run, command, capture_output=True, check=False)
    if result.returncode != 0 or not result.stdout:
        raise HTTPException(status_code=422, detail="Could not read a frame at that time.")
    return Response(result.stdout, media_type="image/jpeg")


@router.post("/youtube/moments", response_model=MomentsOut)
async def youtube_moments(payload: MomentsIn) -> MomentsOut:
    """Find the parts of a YouTube video viewers rewatch or talk about most."""
    settings = _youtube_settings(payload.url, payload.cookies_from_browser)
    try:
        found = await asyncio.to_thread(ingest.find_popular_moments, payload.url, settings)
    except ingest.IngestError as exc:
        raise HTTPException(
            status_code=422, detail={"message": str(exc), "hint": exc.hint}
        ) from exc
    return MomentsOut(**found)


@router.post("/youtube", response_model=SourceOut, status_code=201)
async def ingest_youtube(payload: YouTubeIngestIn) -> SourceOut:
    """Download a YouTube video, or just some sections of it, and register it as a source."""
    settings = _youtube_settings(payload.url, payload.cookies_from_browser)
    sections = [(s.start_s, s.end_s) for s in payload.sections or []]

    try:
        source = await asyncio.to_thread(
            ingest.ingest_youtube, payload.url, settings, sections=sections
        )
    except ingest.IngestError as exc:
        # 422 rather than 500: the request was well-formed, but the content
        # can't be fetched, and the hint tells the user what to change.
        raise HTTPException(
            status_code=422, detail={"message": str(exc), "hint": exc.hint}
        ) from exc

    await asyncio.to_thread(store.create_source, source)
    return SourceOut.of(source)


@router.post("/upload", response_model=SourceOut, status_code=201)
async def upload_source(file: UploadFile = File(...)) -> SourceOut:
    """Accept a media upload and register it as a source."""
    filename = Path(file.filename or "upload")
    suffix = filename.suffix.lower()
    if suffix not in ingest.ACCEPTED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail={
                "message": f"{suffix or 'This file'} is not a supported format.",
                "hint": f"Accepted: {', '.join(sorted(ingest.ACCEPTED_SUFFIXES))}",
            },
        )

    # Stage to a temp file first so a failed or abandoned upload never leaves a
    # half-written file in the media store.
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as staging:
        staging_path = Path(staging.name)
        try:
            while chunk := await file.read(UPLOAD_CHUNK):
                staging.write(chunk)
        except Exception as exc:
            staging_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Upload failed.") from exc

    try:
        source = await asyncio.to_thread(
            ingest.ingest_file, staging_path, move=True, title=filename.stem
        )
    except ingest.IngestError as exc:
        staging_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422, detail={"message": str(exc), "hint": exc.hint}
        ) from exc
    finally:
        shutil.rmtree(staging_path.parent / staging_path.name, ignore_errors=True)

    await asyncio.to_thread(store.create_source, source)
    return SourceOut.of(source)
