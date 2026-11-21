"""Live chat replay — what the stream's chat said during a clip.

Stream clips get one standout chat message as a hook card. The chat comes from
YouTube's live chat replay, fetched only for the clip's few seconds: the replay
API accepts a player offset, so there is no need to page through a whole
24-hour stream's chat to reach one moment.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import IngestSettings

log = logging.getLogger(__name__)

#: Where a sectioned download records which stretches of the original it holds.
SECTIONS_FILE = "sections.json"

#: Stop paging after this many requests — one request covers a few seconds.
_MAX_REQUESTS = 60

#: Card text longer than this doesn't read in three seconds.
_MAX_CARD_CHARS = 70

_NSFW_OR_SPAM = re.compile(
    r"goon|naked|nude|nsfw|boob|sex|porn|https?://|www\.|\.com\b|subscribe to|check my",
    re.I,
)
_WORD = re.compile(r"[A-Za-z']{3,}")


@dataclass(frozen=True)
class ChatMessage:
    t: float  # seconds into the original stream
    author: str
    text: str


# --------------------------------------------------------------------------
# Section offsets
# --------------------------------------------------------------------------


def write_sections(media_dir: Path, sections: list[tuple[float, float]]) -> None:
    (media_dir / SECTIONS_FILE).write_text(json.dumps(sections), encoding="utf-8")


def read_sections(media_dir: Path) -> list[tuple[float, float]] | None:
    path = media_dir / SECTIONS_FILE
    if not path.exists():
        return None
    return [tuple(s) for s in json.loads(path.read_text(encoding="utf-8"))]


def to_original_time(t: float, sections: list[tuple[float, float]] | None) -> float:
    """Map a time in a (possibly sectioned) source file back to the original video."""
    if not sections:
        return t
    elapsed = 0.0
    for start, end in sections:
        length = end - start
        if t < elapsed + length:
            return start + (t - elapsed)
        elapsed += length
    return sections[-1][1]


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def fetch_chat(
    url: str, start_s: float, end_s: float, settings: IngestSettings | None = None
) -> list[ChatMessage]:
    """Return the chat replay messages between two points of a YouTube stream.

    Returns an empty list when the video has no chat replay.
    """
    import yt_dlp
    from yt_dlp.networking import Request

    from .ingest import _ytdlp_options

    settings = settings or IngestSettings()
    with yt_dlp.YoutubeDL(_ytdlp_options(settings)) as ydl:
        ie = ydl.get_info_extractor("Youtube")
        video_id = ie._match_id(url)
        page = ie._download_webpage(url, video_id, note=False)
        data = ie.extract_yt_initial_data(video_id, page)
        ytcfg = ie.extract_ytcfg(video_id, page)
        try:
            continuation = data["contents"]["twoColumnWatchNextResults"]["conversationBar"][
                "liveChatRenderer"
            ]["continuations"][0]["reloadContinuationData"]["continuation"]
        except (KeyError, IndexError, TypeError):
            return []  # not a stream, or the chat replay is off

        context = ytcfg["INNERTUBE_CONTEXT"]
        endpoint = (
            "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat_replay?key="
            + ytcfg["INNERTUBE_API_KEY"]
        )
        headers = ie.generate_api_headers(
            ytcfg=ytcfg, visitor_data=context["client"].get("visitorData")
        ) | {"content-type": "application/json"}

        messages: list[ChatMessage] = []
        offset_ms = start_s * 1000
        for _ in range(_MAX_REQUESTS):
            body = {
                "context": context,
                "continuation": continuation,
                "currentPlayerState": {"playerOffsetMs": str(int(offset_ms))},
            }
            response = json.load(ydl.urlopen(Request(endpoint, json.dumps(body).encode(), headers)))
            chat = response.get("continuationContents", {}).get("liveChatContinuation", {})
            latest = offset_ms
            for action in chat.get("actions", []):
                replay = action.get("replayChatItemAction")
                if not replay:
                    continue
                at_ms = int(replay.get("videoOffsetTimeMsec", 0))
                latest = max(latest, at_ms)
                for inner in replay.get("actions", []):
                    message = _parse_message(inner, at_ms / 1000)
                    if message and start_s <= message.t <= end_s:
                        messages.append(message)
            nxt = (chat.get("continuations") or [{}])[0].get("liveChatReplayContinuationData", {})
            if not nxt.get("continuation") or latest <= offset_ms or latest >= end_s * 1000:
                break
            continuation, offset_ms = nxt["continuation"], latest + 1
    return messages


def _parse_message(action: dict, t: float) -> ChatMessage | None:
    renderer = (
        action.get("addChatItemAction", {}).get("item", {}).get("liveChatTextMessageRenderer")
    )
    if not renderer:
        return None
    parts = []
    for run in renderer.get("message", {}).get("runs", []):
        if "text" in run:
            parts.append(run["text"])
        elif 0 < len(emoji_id := run.get("emoji", {}).get("emojiId", "")) <= 4:
            # Standard emoji carry the character itself; channel emotes carry a long ID.
            parts.append(emoji_id)
    text = "".join(parts).strip()
    if not text:
        return None
    return ChatMessage(t=t, author=renderer.get("authorName", {}).get("simpleText", ""), text=text)


#: Per-source cache of timestamped top comments — fetching them takes ~30s.
COMMENTS_FILE = "comments.json"


def comment_messages(
    url: str, media_dir: Path, settings: IngestSettings | None = None
) -> list[ChatMessage]:
    """Top comments that mention a timestamp, as messages at that moment.

    The fallback for streams with no chat replay (YouTube drops it on some
    very long streams): viewers still write "20:21:33 red hulk wtf".
    """
    cache = media_dir / COMMENTS_FILE
    if cache.exists():
        rows = json.loads(cache.read_text(encoding="utf-8"))
        return [ChatMessage(**row) for row in rows]

    import yt_dlp

    from .ingest import _MAX_STAMPS_PER_COMMENT, _TIMESTAMP, _ytdlp_options

    options = _ytdlp_options(settings or IngestSettings()) | {
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {
            "youtube": {"comment_sort": ["top"], "max_comments": ["1000", "all", "0"]}
        },
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False) or {}

    messages = []
    for c in info.get("comments") or []:
        text = (c.get("text") or "").replace("\n", " ")
        stamps = _TIMESTAMP.findall(text)
        if not stamps or len(stamps) > _MAX_STAMPS_PER_COMMENT:
            continue
        body = re.sub(r"[\s()\[\]-]+", " ", _TIMESTAMP.sub("", text)).strip()
        for h, m, s in stamps:
            t = int(h or 0) * 3600 + int(m) * 60 + int(s)
            messages.append(ChatMessage(t=float(t), author=c.get("author") or "", text=body))
    cache.write_text(json.dumps([m.__dict__ for m in messages]), encoding="utf-8")
    return messages


# --------------------------------------------------------------------------
# Picking the card
# --------------------------------------------------------------------------


def pick_card(messages: list[ChatMessage]) -> ChatMessage | None:
    """Pick the chat message that best captures the moment, or None.

    Chat during a hype moment is mostly one-word spam ("W", "LMAO"). The best
    card is a readable message that says what everyone else is reacting to: it
    shares words with many other messages, and shouts a little.
    ponytail: word-overlap heuristic; swap for an LLM pick if cards read flat.
    """
    words_per_message = [{w.lower() for w in _WORD.findall(m.text)} for m in messages]
    counts: dict[str, int] = {}
    for words in words_per_message:
        for w in words:
            counts[w] = counts.get(w, 0) + 1

    best, best_score = None, 0.0
    for message, words in zip(messages, words_per_message, strict=True):
        text = message.text
        if not (8 <= len(text) <= _MAX_CARD_CHARS) or len(words) < 2:
            continue
        if _NSFW_OR_SPAM.search(text) or text.startswith("@"):
            continue
        echo = sum(counts[w] - 1 for w in words)
        letters = [c for c in text if c.isalpha()]
        caps = sum(c.isupper() for c in letters) / len(letters) if letters else 0
        score = echo + 3 * caps + (2 if any(e in text for e in "💀😭🔥😂!?") else 0)
        if score > best_score:
            best, best_score = message, score
    return best
