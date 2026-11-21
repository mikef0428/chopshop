"""Stream clips: chat time mapping, the chat card, saved layouts, and the stacked render graph."""

from __future__ import annotations

from pathlib import Path

from autoclip.pipeline import captions, export
from autoclip.pipeline.chat import ChatMessage, _parse_message, pick_card, to_original_time
from autoclip.pipeline.reframe.croppath import centre_crop
from autoclip.pipeline.reframe.facecam import Box, StreamLayout, load_layout, save_layout


def test_sectioned_time_maps_back_to_the_original_stream() -> None:
    sections = [(3420.0, 3960.0), (70020.0, 70620.0)]  # 9 min, then 10 min

    assert to_original_time(60, sections) == 3480
    assert to_original_time(540 + 300, sections) == 70320
    assert to_original_time(5, None) == 5


def _msg(text: str) -> ChatMessage:
    return ChatMessage(t=0, author="@someone", text=text)


def test_card_skips_spam_and_picks_what_chat_is_reacting_to() -> None:
    chat = [_msg("W"), _msg("w"), _msg("LMAO"), _msg("bro the CAR just flew"), _msg("car flew lol")]
    chat += [_msg("check my channel for car clips https://x.co"), _msg("the car glitch is insane")]

    card = pick_card(chat)

    assert card is not None and "car" in card.text.lower()
    assert "http" not in card.text


def test_no_card_when_chat_is_only_spam() -> None:
    assert pick_card([_msg("W"), _msg("W"), _msg("😂")]) is None


def test_chat_message_keeps_standard_emoji_and_drops_channel_emotes() -> None:
    action = {
        "addChatItemAction": {
            "item": {
                "liveChatTextMessageRenderer": {
                    "authorName": {"simpleText": "@fan"},
                    "message": {
                        "runs": [
                            {"text": "NO WAY "},
                            {"emoji": {"emojiId": "💀"}},
                            {"emoji": {"emojiId": "UCabc/emote123"}},
                        ]
                    },
                }
            }
        }
    }

    assert _parse_message(action, 12.0) == ChatMessage(12.0, "@fan", "NO WAY 💀")


def test_layout_round_trips(tmp_path: Path) -> None:
    layout = StreamLayout(Box(20, 460, 368, 240), Box(400, 0, 1300, 1080), origin="drawn")

    save_layout(tmp_path, layout)

    assert load_layout(tmp_path) == layout
    assert load_layout(tmp_path / "missing") is None


def test_stream_graph_stacks_camera_over_gameplay() -> None:
    request = export.ExportRequest(
        source=Path("in.mp4"),
        destination=Path("out.mp4"),
        start_s=0,
        end_s=20,
        crop_path=centre_crop(1920, 1080, 20),
        words=[],
        style=captions.get_style("bold_pop"),
        stream=StreamLayout(Box(20, 460, 368, 240), Box(0, 0, 1920, 1080)),
    )

    graph = export.build_video_filtergraph(request, subtitle_name="captions.ass")

    cam_h = export.stream_cam_height(request.stream.cam, 1080, 1920)
    assert 0.28 * 1920 <= cam_h <= 0.45 * 1920
    assert f"scale=1080:{cam_h}" in graph and f"scale=1080:{1920 - cam_h}" in graph
    assert "vstack=inputs=2" in graph
    assert graph.endswith("ass=filename=captions.ass:fontsdir=fonts[vout]")


def test_captions_sit_on_the_seam_and_the_card_shows_first() -> None:
    subs = captions.build_ass(
        [], captions.get_style("bold_pop"), width=1080, height=1920, seam_y=700, card="NO WAY 💀"
    )

    style = subs.styles[captions.STYLE_NAME]
    assert 1920 - 700 - style.fontsize <= style.marginv <= 1920 - 700
    (card,) = subs.events
    assert card.style == captions.CARD_STYLE and card.start == 0
    assert card.end == captions.CARD_SECONDS * 1000 and "NO WAY" in card.text
