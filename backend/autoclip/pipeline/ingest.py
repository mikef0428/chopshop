"""Ingestion — YouTube URLs and local file uploads become source records.

Both paths converge on a validated :class:`~autoclip.db.models.Source` with a
file on disk and probed metadata.

A note on YouTube: as of 2026 most anonymous downloads hit a bot check, and
proof-of-origin tokens no longer clear it reliably — browser cookies do. So
:class:`IngestError` distinguishes that specific failure and tells the user how
to fix it, rather than surfacing a raw yt-dlp traceback.
"""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from .. import paths
from ..config import IngestSettings
from ..db.models import Source, new_id
from . import chat, ffmpeg

log = logging.getLogger(__name__)

#: Container and audio formats we accept for upload.
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
ACCEPTED_SUFFIXES = VIDEO_SUFFIXES | AUDIO_SUFFIXES

_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")
_TWITCH_HOSTS = ("twitch.tv", "www.twitch.tv", "m.twitch.tv")
_TWITCH_VOD_PATH = re.compile(r"^/videos/(\d+)/?$")

#: yt-dlp error fragments that mean "YouTube wants proof you're a human".
_BOT_CHECK_MARKERS = (
    "sign in to confirm",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "this content isn't available",
    "player response",
)


class IngestError(RuntimeError):
    """Ingestion failed in a way worth explaining to the user."""

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base}\n\n{self.hint}" if self.hint else base


def is_youtube_url(url: str) -> bool:
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _YOUTUBE_HOSTS


def is_twitch_url(url: str) -> bool:
    from urllib.parse import urlparse

    try:
        return (urlparse(url).hostname or "").lower() in _TWITCH_HOSTS
    except ValueError:
        return False


def twitch_vod_id(url: str) -> str | None:
    """The VOD id of a twitch.tv/videos/<id> link, or None for anything else."""
    from urllib.parse import urlparse

    if not is_twitch_url(url):
        return None
    match = _TWITCH_VOD_PATH.match(urlparse(url).path)
    return match.group(1) if match else None


def is_supported_url(url: str) -> bool:
    """A link we can download: YouTube, or a Twitch past broadcast."""
    return is_youtube_url(url) or twitch_vod_id(url) is not None


def slugify(text: str, *, max_length: int = 60) -> str:
    """Turn a title into a filesystem- and URL-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:max_length] or "clip"


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------


def _ytdlp_options(settings: IngestSettings, url: str) -> dict:
    """Options every request shares: quiet, JS runtimes, and (YouTube only) cookies."""
    options: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # YouTube's player challenges need a JS runtime. yt-dlp only enables
        # Deno by default; Node is far more commonly installed, so allow both.
        "js_runtimes": {"deno": {}, "node": {}},
    }
    if settings.cookies_from_browser and is_youtube_url(url):
        # yt-dlp expects a tuple; only the browser name is required.
        options["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    return options


def normalize_sections(sections: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sort sections, drop empty ones, and merge any that overlap or touch."""
    merged: list[tuple[float, float]] = []
    for start, end in sorted((max(0.0, s), e) for s, e in sections if e > max(0.0, s)):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def ingest_youtube(
    url: str,
    settings: IngestSettings | None = None,
    *,
    sections: list[tuple[float, float]] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Source:
    """Download a YouTube video and return a validated source record.

    ``sections`` limits the download to those (start_s, end_s) ranges, joined
    in order into one source file — so a 24-hour stream can be clipped from
    just its best stretches.

    Preconditions:
        url points at content the user owns or has the rights to process.
    """
    import yt_dlp

    if is_twitch_url(url) and twitch_vod_id(url) is None:
        raise IngestError(
            "That is a Twitch channel or live link.",
            hint="Paste the link to a past broadcast, like twitch.tv/videos/123456789.",
        )

    settings = settings or IngestSettings()
    sections = normalize_sections(sections or [])
    source_id = new_id()
    target_dir = paths.source_media_dir(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    def hook(status: dict) -> None:
        if not on_progress or status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        done = status.get("downloaded_bytes")
        if total and done:
            on_progress(min(1.0, done / total))

    options = _ytdlp_options(settings, url) | {
        "format": settings.ytdlp_format,
        "outtmpl": str(target_dir / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "retries": 3,
        "fragment_retries": 3,
    }
    if sections:
        # Prefer HLS for ranges: it arrives in short segments, which survives
        # long videos far better than one long ranged read of a DASH stream.
        options["format"] = f"b[height<=1080][protocol^=m3u8]/{settings.ytdlp_format}"
        options["download_ranges"] = yt_dlp.utils.download_range_func(None, sections)
        # yt-dlp cuts ranges with ffmpeg, which treats a dropped connection as
        # end-of-stream and stops early without an error. Make it reconnect.
        options["external_downloader_args"] = {
            "ffmpeg_i": [
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_on_network_error", "1",
                "-reconnect_delay_max", "10",
            ]
        }  # fmt: skip
        # One file per section, named so they sort in timeline order.
        options["outtmpl"] = str(target_dir / "section_%(section_start)09d.%(ext)s")
    if settings.prefer_youtube_captions and is_youtube_url(url) and not sections:
        # Captions would be timed against the full video, not the joined sections.
        options["writeautomaticsub"] = True
        options["subtitleslangs"] = ["en.*"]
        options["subtitlesformat"] = "json3"

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            metadata = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise _translate_ytdlp_error(exc, settings, url) from exc
    except Exception as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise IngestError(f"Could not download {url}: {exc}") from exc

    if sections:
        try:
            # Ranges past the end of the video come back only as long as the video.
            full = float((metadata or {}).get("duration") or 0)
            expected = [(s, min(e, full)) for s, e in sections] if full else sections
            _join_sections(target_dir, expected)
            # Lets stream clips map their time back to the original (for chat).
            chat.write_sections(target_dir, expected)
        except ffmpeg.FFmpegError as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise IngestError("Could not join the downloaded sections.", hint=str(exc)) from exc
        except IngestError:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise

    downloaded = _find_downloaded_file(target_dir)
    if downloaded is None:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise IngestError("yt-dlp reported success but produced no media file.")

    info = _probe_and_validate(downloaded)
    title = (metadata or {}).get("title") or downloaded.stem
    if sections:
        title = f"{title} · {len(sections)} section{'s' if len(sections) != 1 else ''}"

    return Source(
        id=source_id,
        # ponytail: 'youtube' means "fetched by yt-dlp"; add a 'twitch' type with a
        # table-rebuild migration when the self-serve site needs to tell them apart.
        type="youtube",
        url=url,
        path=str(downloaded),
        filename=downloaded.name,
        title=title,
        channel=(metadata or {}).get("uploader") or (metadata or {}).get("channel"),
        duration_s=info.duration_s or float((metadata or {}).get("duration") or 0.0),
        width=info.width,
        height=info.height,
        fps=info.fps,
        has_audio=info.has_audio,
        has_video=info.has_video,
    )


def _translate_ytdlp_error(
    exc: Exception, settings: IngestSettings, url: str = ""
) -> IngestError:
    """Turn a yt-dlp failure into something the user can act on."""
    message = str(exc).lower()

    if is_twitch_url(url):
        return IngestError(
            "Twitch refused this download.",
            hint=(
                "Check that the past broadcast still exists and is public. Twitch deletes "
                "past broadcasts after a while. If it keeps failing, run "
                "`chopshop update-ytdlp`.\n\n"
                f"Original error: {exc}"
            ),
        )

    if any(marker in message for marker in _BOT_CHECK_MARKERS):
        if settings.cookies_from_browser:
            hint = (
                f"Cookies are already being read from {settings.cookies_from_browser}, but "
                "YouTube still refused. Make sure you are signed in to YouTube in that "
                "browser and that the browser is fully closed — it locks its cookie "
                "database while running."
            )
        else:
            hint = (
                "YouTube is asking for proof you're not a bot. Set a browser to pull "
                "cookies from — in Settings, or via config.json's "
                '`ingest.cookies_from_browser` (e.g. "chrome", "firefox", "edge"). '
                "You must be signed in to YouTube in that browser, and it must be closed "
                "while Chop Shop downloads."
            )
        return IngestError("YouTube blocked this download with a bot check.", hint=hint)

    if "private video" in message or "members-only" in message:
        return IngestError(
            "This video is private or members-only.",
            hint="Chop Shop only downloads content you can access and have the rights to use.",
        )
    if "unavailable" in message or "removed" in message:
        return IngestError("This video is unavailable or has been removed.")
    if "drm" in message:
        return IngestError(
            "This content is DRM-protected.",
            hint="Chop Shop does not and will not circumvent DRM.",
        )

    return IngestError(
        "yt-dlp could not download this video.",
        hint=(
            "YouTube changes frequently and yt-dlp is updated often. Try "
            "`autoclip update-ytdlp` to pull the latest version.\n\n"
            f"Original error: {exc}"
        ),
    )


#: A section this much shorter than requested was cut off mid-download.
_MIN_SECTION_FRACTION = 0.9


def _join_sections(directory: Path, sections: list[tuple[float, float]]) -> None:
    """Check the section_* files yt-dlp wrote, then concatenate them into one source."""
    parts = sorted(p for p in directory.glob("section_*") if p.suffix.lower() in ACCEPTED_SUFFIXES)
    if not parts:
        return
    if len(parts) != len(sections):
        raise IngestError(f"Asked for {len(sections)} sections but got {len(parts)}.")
    for part, (start, end) in zip(parts, sections, strict=True):
        try:
            got = ffmpeg.probe(part).duration_s
        except ffmpeg.FFmpegError:
            got = 0.0
        if got < (end - start) * _MIN_SECTION_FRACTION:
            raise IngestError(
                f"YouTube cut the section starting at {_clock(start)} short "
                f"({got:.0f}s of {end - start:.0f}s).",
                hint="This is usually a dropped connection. Try again in a few minutes.",
            )
    target = directory / f"source{parts[0].suffix}"
    if len(parts) == 1:
        parts[0].rename(target)
        return
    # Same stream, same format, so the concat demuxer can join without re-encoding.
    listing = directory / "sections.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    ffmpeg.run(
        ["-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy", target.name],
        cwd=directory,
    )
    for p in [*parts, listing]:
        p.unlink(missing_ok=True)


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


# --------------------------------------------------------------------------
# Popular moments
# --------------------------------------------------------------------------

#: H:MM:SS or M:SS / MM:SS, as viewers type them in comments.
_TIMESTAMP = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)(?![\d:])")

#: Comment words that usually point at nudity or sexual content — moments a
#: clip channel should skip, since they get Shorts age-restricted or removed.
#: ponytail: keyword list, swap for a classifier if it flags too much or too little.
_NSFW = re.compile(
    r"goon|naked|nude|nsfw|blur|boob|thank me later|tnx me|ur welcome|you're welcome"
    r"|your welcome|kids (?:pls|please) don|🌚|🥵|💦",
    re.I,
)

#: Comments listing more than this many timestamps are chapter lists, not reactions.
_MAX_STAMPS_PER_COMMENT = 3
#: Mentions closer than this together count as the same moment.
_CLUSTER_GAP_S = 90.0
#: Lead-in and tail around a moment, so the clip has its setup and payoff.
_LEAD_S, _TAIL_S = 60.0, 120.0


def find_popular_moments(
    url: str, settings: IngestSettings | None = None, *, limit: int = 10
) -> dict:
    """Find the stretches of a video viewers rewatch or talk about most.

    Uses YouTube's "most replayed" heatmap when the video has one, and falls
    back to timestamps viewers wrote in the top comments (long live-stream
    VODs usually have no heatmap).
    """
    import yt_dlp

    if is_twitch_url(url):
        # No replay heatmap or top comments to mine on Twitch.
        return {"title": "", "duration_s": 0.0, "moments": []}

    settings = settings or IngestSettings()
    base = _ytdlp_options(settings, url) | {"skip_download": True}

    try:
        with yt_dlp.YoutubeDL(base) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        duration = float(info.get("duration") or 0)
        moments = moments_from_heatmap(info.get("heatmap") or [], duration, limit=limit)
        if not moments:
            comment_options = base | {
                "getcomments": True,
                "extractor_args": {
                    "youtube": {"comment_sort": ["top"], "max_comments": ["1000", "all", "0"]}
                },
            }
            with yt_dlp.YoutubeDL(comment_options) as ydl:
                info = ydl.extract_info(url, download=False) or info
            moments = moments_from_comments(info.get("comments") or [], duration, limit=limit)
    except yt_dlp.utils.DownloadError as exc:
        raise _translate_ytdlp_error(exc, settings) from exc

    return {"title": info.get("title") or "", "duration_s": duration, "moments": moments}


def moments_from_heatmap(points: list[dict], duration: float, *, limit: int = 10) -> list[dict]:
    """Merge the hottest heatmap segments into moments, hottest first."""
    if not points:
        return []
    values = sorted(p["value"] for p in points)
    threshold = values[int(len(values) * 0.85)]  # top ~15% of the timeline
    moments: list[dict] = []
    for p in sorted(points, key=lambda p: p["start_time"]):
        if p["value"] < threshold:
            continue
        if moments and p["start_time"] <= moments[-1]["end_s"]:
            moments[-1]["end_s"] = p["end_time"]
            moments[-1]["score"] = max(moments[-1]["score"], p["value"])
        else:
            moments.append(
                {
                    "start_s": p["start_time"],
                    "end_s": p["end_time"],
                    "score": p["value"],
                    "source": "replays",
                    "quotes": [],
                    "flagged": False,
                }
            )
    return sorted(moments, key=lambda m: -m["score"])[:limit]


def moments_from_comments(comments: list[dict], duration: float, *, limit: int = 10) -> list[dict]:
    """Cluster timestamps viewers wrote in comments into moments, most-talked-about first."""
    mentions: list[tuple[float, int, str]] = []
    for c in comments:
        text = (c.get("text") or "").replace("\n", " ")
        stamps = _TIMESTAMP.findall(text)
        if not stamps or len(stamps) > _MAX_STAMPS_PER_COMMENT:
            continue
        for h, m, s in stamps:
            t = int(h or 0) * 3600 + int(m) * 60 + int(s)
            if 0 < t < (duration or float("inf")):
                mentions.append((float(t), int(c.get("like_count") or 0), text))

    clusters: list[list[tuple[float, int, str]]] = []
    for mention in sorted(mentions):
        if clusters and mention[0] - clusters[-1][-1][0] <= _CLUSTER_GAP_S:
            clusters[-1].append(mention)
        else:
            clusters.append([mention])

    moments = []
    for cluster in clusters:
        times = [t for t, _, _ in cluster]
        quotes = [text for _, _, text in sorted(cluster, key=lambda x: -x[1])]
        moments.append(
            {
                "start_s": max(0.0, min(times) - _LEAD_S),
                "end_s": min(duration, max(times) + _TAIL_S) if duration else max(times) + _TAIL_S,
                # A mention is worth a lot more than a like on someone else's mention.
                "score": len(cluster) * 20 + sum(likes for _, likes, _ in cluster),
                "source": "comments",
                "quotes": list(dict.fromkeys(quotes))[:3],
                "flagged": any(_NSFW.search(text) for _, _, text in cluster),
            }
        )
    return sorted(moments, key=lambda m: -m["score"])[:limit]


def _find_downloaded_file(directory: Path) -> Path | None:
    """Return the largest media file in a directory, ignoring sidecars."""
    candidates = [
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in ACCEPTED_SUFFIXES
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------


def ingest_file(path: Path, *, move: bool = False, title: str | None = None) -> Source:
    """Register a local file as a source, copying it into AutoClip's media store.

    Copying rather than referencing in place means a job stays reproducible even
    if the user moves or deletes the original.

    Preconditions:
        path exists and is a readable media file.
    """
    path = Path(path)
    if not path.exists():
        raise IngestError(f"{path} does not exist.")
    if not path.is_file():
        raise IngestError(f"{path} is not a file.")

    suffix = path.suffix.lower()
    if suffix not in ACCEPTED_SUFFIXES:
        accepted = ", ".join(sorted(ACCEPTED_SUFFIXES))
        raise IngestError(
            f"{suffix or 'This file'} is not a supported format.",
            hint=f"Accepted formats: {accepted}",
        )

    source_id = new_id()
    target_dir = paths.source_media_dir(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{suffix}"

    try:
        if move:
            shutil.move(str(path), target)
        else:
            shutil.copy2(path, target)
    except OSError as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise IngestError(f"Could not store {path.name}: {exc}") from exc

    try:
        info = _probe_and_validate(target)
    except Exception:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise

    return Source(
        id=source_id,
        type="upload",
        path=str(target),
        filename=path.name,
        title=title or info.title or path.stem,
        duration_s=info.duration_s,
        width=info.width,
        height=info.height,
        fps=info.fps,
        has_audio=info.has_audio,
        has_video=info.has_video,
    )


def _probe_and_validate(path: Path) -> ffmpeg.MediaInfo:
    """Probe a media file and reject anything the pipeline can't process."""
    try:
        info = ffmpeg.probe(path)
    except ffmpeg.FFmpegError as exc:
        raise IngestError(f"{path.name} could not be read as media.", hint=str(exc)) from exc

    if not info.has_audio:
        raise IngestError(
            f"{path.name} has no audio track.",
            hint=(
                "Chop Shop finds clips by transcribing speech, so a file with no audio "
                "has nothing to work from."
            ),
        )
    if info.duration_s <= 0:
        raise IngestError(
            f"{path.name} reports zero duration.",
            hint="The file may be corrupt or still being written.",
        )

    return info
