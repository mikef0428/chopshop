"""Section downloads and popular-moment detection — the pure parts, no network."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from autoclip.pipeline import ffmpeg
from autoclip.pipeline.ingest import (
    IngestError,
    _join_sections,
    moments_from_comments,
    moments_from_heatmap,
    normalize_sections,
)


def _make_part(path: Path, seconds: int) -> None:
    subprocess.run(
        [ffmpeg.ffmpeg_path(), "-v", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc2=size=64x64:rate=10:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=duration={seconds}",
         "-shortest", "-c:v", "libx264", "-c:a", "aac", str(path)],
        check=True,
    )  # fmt: skip


def test_sections_are_checked_and_joined(tmp_path: Path) -> None:
    _make_part(tmp_path / "section_000000000.mp4", 2)
    _make_part(tmp_path / "section_000000010.mp4", 2)

    _join_sections(tmp_path, [(0, 2), (10, 12)])

    assert [p.name for p in tmp_path.iterdir()] == ["source.mp4"]
    assert ffmpeg.probe(tmp_path / "source.mp4").duration_s == pytest.approx(4, abs=0.3)


def test_a_cut_short_section_is_an_error_not_a_shorter_video(tmp_path: Path) -> None:
    _make_part(tmp_path / "section_000000000.mp4", 2)

    with pytest.raises(IngestError, match="short"):
        _join_sections(tmp_path, [(0, 10)])


def test_sections_are_sorted_merged_and_cleaned() -> None:
    raw = [(600, 900), (-5, 60), (50, 120), (300, 300), (900, 1000)]

    assert normalize_sections(raw) == [(0.0, 120), (600, 1000)]


def _comment(text: str, likes: int = 0) -> dict:
    return {"text": text, "like_count": likes}


def test_comment_timestamps_cluster_into_moments() -> None:
    comments = [
        _comment("1:00:05 the glitch 😂", likes=30),
        _comment("1:00:40 he had no idea", likes=5),
        _comment("2:15:00 lmao", likes=1),
        # A chapter list is not a reaction, so it is ignored.
        _comment("0:10:00 intro 0:20:00 heist 0:30:00 chase 0:40:00 boss"),
    ]

    moments = moments_from_comments(comments, duration=10_000)

    assert len(moments) == 2
    top = moments[0]
    assert (top["start_s"], top["end_s"]) == (3605 - 60, 3640 + 120)
    assert top["quotes"][0].startswith("1:00:05")
    assert not top["flagged"]


def test_nsfw_comments_flag_the_moment() -> None:
    moments = moments_from_comments([_comment("3:32:29 this gonna get blurred")], duration=20_000)

    assert moments[0]["flagged"]


def test_timestamps_past_the_end_are_ignored() -> None:
    assert moments_from_comments([_comment("5:00:00 wow")], duration=3600) == []


def test_heatmap_keeps_only_the_hottest_stretches() -> None:
    points = [{"start_time": i * 10.0, "end_time": (i + 1) * 10.0, "value": 0.1} for i in range(20)]
    points[5]["value"] = points[6]["value"] = 1.0  # one hot stretch, 50-70s
    points[15]["value"] = 0.9

    moments = moments_from_heatmap(points, duration=200)

    assert [(m["start_s"], m["end_s"]) for m in moments] == [(50.0, 70.0), (150.0, 160.0)]
    assert moments[0]["source"] == "replays"
