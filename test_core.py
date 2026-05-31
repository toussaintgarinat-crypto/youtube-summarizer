"""Unit tests for youtube-summarizer core modules (no external API calls)."""

import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/Users/garinat_t/Desktop/youtube-summarizer")

# ─────────────────────────────────────────────────────────────
# extractor.py
# ─────────────────────────────────────────────────────────────
from src.extractor import (
    detect_platform,
    extract_youtube_id,
    extract_twitch_id,
    extract_vimeo_id,
    validate_url,
    get_supported_platforms,
)


class TestDetectPlatform(unittest.TestCase):
    def test_youtube_watch(self):
        self.assertEqual(detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "youtube")

    def test_youtu_be_short(self):
        self.assertEqual(detect_platform("https://youtu.be/dQw4w9WgXcQ"), "youtube")

    def test_youtube_nocookie(self):
        self.assertEqual(detect_platform("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"), "youtube")

    def test_twitch_vod(self):
        self.assertEqual(detect_platform("https://www.twitch.tv/videos/123456789"), "twitch")

    def test_twitch_clip(self):
        self.assertEqual(detect_platform("https://clips.twitch.tv/SomeName"), "twitch")

    def test_vimeo(self):
        self.assertEqual(detect_platform("https://vimeo.com/123456"), "vimeo")

    def test_unknown(self):
        self.assertEqual(detect_platform("https://example.com/video"), "unknown")

    def test_tiktok_unknown(self):
        self.assertEqual(detect_platform("https://www.tiktok.com/@user/video/123"), "unknown")


class TestExtractYoutubeId(unittest.TestCase):
    def test_watch_url(self):
        self.assertEqual(extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_short_url(self):
        self.assertEqual(extract_youtube_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_embed_url(self):
        self.assertEqual(extract_youtube_id("https://www.youtube.com/embed/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_raw_id(self):
        self.assertEqual(extract_youtube_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_url_with_extra_params(self):
        self.assertEqual(
            extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30"),
            "dQw4w9WgXcQ",
        )

    def test_invalid(self):
        self.assertIsNone(extract_youtube_id("https://www.youtube.com/channel/UCxxx"))

    def test_short_id_too_short(self):
        self.assertIsNone(extract_youtube_id("short"))


class TestExtractTwitchId(unittest.TestCase):
    def test_vod(self):
        vid, vtype = extract_twitch_id("https://www.twitch.tv/videos/123456789")
        self.assertEqual(vid, "123456789")
        self.assertEqual(vtype, "video")

    def test_clip(self):
        vid, vtype = extract_twitch_id("https://www.twitch.tv/streamer/clip/AwkwardClipName")
        self.assertEqual(vid, "AwkwardClipName")
        self.assertEqual(vtype, "clip")

    def test_channel(self):
        vid, vtype = extract_twitch_id("https://www.twitch.tv/somestreamer")
        self.assertEqual(vid, "somestreamer")
        self.assertEqual(vtype, "channel")

    def test_invalid(self):
        vid, vtype = extract_twitch_id("https://example.com/nope")
        self.assertIsNone(vid)
        self.assertIsNone(vtype)


class TestExtractVimeoId(unittest.TestCase):
    def test_standard(self):
        self.assertEqual(extract_vimeo_id("https://vimeo.com/123456789"), "123456789")

    def test_player(self):
        self.assertEqual(extract_vimeo_id("https://player.vimeo.com/video/987654321"), "987654321")

    def test_invalid(self):
        self.assertIsNone(extract_vimeo_id("https://example.com/nope"))


class TestValidateUrl(unittest.TestCase):
    def test_valid_youtube(self):
        ok, msg = validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(ok)
        self.assertIn("YouTube", msg)

    def test_valid_twitch_vod(self):
        ok, msg = validate_url("https://www.twitch.tv/videos/123456789")
        self.assertTrue(ok)

    def test_valid_vimeo(self):
        ok, msg = validate_url("https://vimeo.com/123456789")
        self.assertTrue(ok)

    def test_empty_url(self):
        ok, msg = validate_url("")
        self.assertFalse(ok)

    def test_whitespace_url(self):
        ok, msg = validate_url("   ")
        self.assertFalse(ok)

    def test_youtube_channel_rejected(self):
        ok, msg = validate_url("https://www.youtube.com/channel/UCxxx")
        self.assertFalse(ok)

    def test_youtube_user_rejected(self):
        ok, msg = validate_url("https://www.youtube.com/user/SomeUser")
        self.assertFalse(ok)

    def test_youtube_at_channel_rejected(self):
        ok, msg = validate_url("https://www.youtube.com/@SomeChannel")
        self.assertFalse(ok)

    def test_youtube_playlist_rejected(self):
        ok, msg = validate_url("https://www.youtube.com/playlist?list=PL123")
        self.assertFalse(ok)

    def test_unknown_platform_rejected(self):
        ok, msg = validate_url("https://example.com/video/123")
        self.assertFalse(ok)


class TestGetSupportedPlatforms(unittest.TestCase):
    def test_returns_list(self):
        platforms = get_supported_platforms()
        self.assertIsInstance(platforms, list)
        self.assertGreater(len(platforms), 0)

    def test_has_required_keys(self):
        for p in get_supported_platforms():
            self.assertIn("id", p)
            self.assertIn("name", p)
            self.assertIn("icon", p)

    def test_youtube_present(self):
        ids = [p["id"] for p in get_supported_platforms()]
        self.assertIn("youtube", ids)


# ─────────────────────────────────────────────────────────────
# chunker.py
# ─────────────────────────────────────────────────────────────
from src.chunker import (
    estimate_tokens,
    format_timestamp,
    create_text_from_transcript,
    chunk_transcript,
    get_chunk_count_info,
)


class TestFormatTimestamp(unittest.TestCase):
    def test_seconds_only(self):
        self.assertEqual(format_timestamp(45), "00:45")

    def test_one_minute(self):
        self.assertEqual(format_timestamp(90), "01:30")

    def test_one_hour(self):
        self.assertEqual(format_timestamp(3661), "01:01:01")

    def test_zero(self):
        self.assertEqual(format_timestamp(0), "00:00")


class TestEstimateTokens(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_short_text(self):
        count = estimate_tokens("Hello world")
        self.assertGreater(count, 0)

    def test_longer_text(self):
        count = estimate_tokens("Hello world " * 100)
        self.assertGreater(count, 100)


class TestCreateTextFromTranscript(unittest.TestCase):
    def _make_entry(self, text, start, duration=5.0):
        return {"text": text, "start": start, "duration": duration}

    def test_single_entry(self):
        t = [self._make_entry("Hello world", 0)]
        text = create_text_from_transcript(t)
        self.assertIn("Hello world", text)
        self.assertIn("[00:00]", text)

    def test_multiple_entries(self):
        t = [
            self._make_entry("First", 0),
            self._make_entry("Second", 60),
        ]
        text = create_text_from_transcript(t)
        self.assertIn("First", text)
        self.assertIn("Second", text)
        self.assertIn("[01:00]", text)

    def test_empty_transcript(self):
        text = create_text_from_transcript([])
        self.assertEqual(text, "")


class TestChunkTranscript(unittest.TestCase):
    def _make_entry(self, text, start, duration=5.0):
        return {"text": text, "start": start, "duration": duration}

    def test_empty_transcript(self):
        self.assertEqual(chunk_transcript([]), [])

    def test_single_chunk_when_small(self):
        transcript = [self._make_entry(f"word{i}", i * 5) for i in range(5)]
        chunks = chunk_transcript(transcript, max_tokens=10000, overlap_tokens=100)
        self.assertEqual(len(chunks), 1)
        self.assertIn("text", chunks[0])
        self.assertIn("start", chunks[0])
        self.assertIn("end", chunks[0])

    def test_multiple_chunks_when_large(self):
        # Create a large transcript that needs chunking
        long_text = "This is a long sentence with many words. " * 20
        transcript = [self._make_entry(long_text, i * 5) for i in range(50)]
        chunks = chunk_transcript(transcript, max_tokens=200, overlap_tokens=20)
        self.assertGreater(len(chunks), 1)

    def test_chunk_has_required_keys(self):
        transcript = [self._make_entry("Hello world", i * 5) for i in range(3)]
        chunks = chunk_transcript(transcript, max_tokens=10000)
        for chunk in chunks:
            self.assertIn("text", chunk)
            self.assertIn("start", chunk)
            self.assertIn("end", chunk)
            self.assertIn("tokens", chunk)

    def test_chunks_cover_all_content(self):
        transcript = [self._make_entry(f"segment {i}", i * 5) for i in range(10)]
        chunks = chunk_transcript(transcript, max_tokens=10000)
        full_text = " ".join(c["text"] for c in chunks)
        for i in range(10):
            self.assertIn(f"segment {i}", full_text)

    def test_no_infinite_loop_single_large_entry(self):
        """A single entry that exceeds max_tokens must not loop forever."""
        huge_text = "word " * 5000
        transcript = [self._make_entry(huge_text, 0)]
        chunks = chunk_transcript(transcript, max_tokens=100, overlap_tokens=10)
        self.assertGreater(len(chunks), 0)


class TestGetChunkCountInfo(unittest.TestCase):
    def test_single_chunk(self):
        chunks = [{"tokens": 500}]
        info = get_chunk_count_info(chunks)
        self.assertIn("1 chunk", info)
        self.assertIn("500", info)

    def test_multiple_chunks(self):
        chunks = [{"tokens": 300}, {"tokens": 400}]
        info = get_chunk_count_info(chunks)
        self.assertIn("2 chunks", info)
        self.assertIn("700", info)


# ─────────────────────────────────────────────────────────────
# utils.py
# ─────────────────────────────────────────────────────────────
from src.utils import (
    extract_video_id,
    validate_youtube_url,
    parse_markdown_sections,
    format_duration,
    clean_text,
)


class TestExtractVideoId(unittest.TestCase):
    def test_watch_url(self):
        self.assertEqual(extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_short_url(self):
        self.assertEqual(extract_video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_raw_id(self):
        self.assertEqual(extract_video_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_invalid(self):
        self.assertIsNone(extract_video_id("not-a-url"))


class TestValidateYoutubeUrl(unittest.TestCase):
    def test_valid(self):
        ok, vid = validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(ok)
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_empty(self):
        ok, msg = validate_youtube_url("")
        self.assertFalse(ok)

    def test_invalid(self):
        ok, msg = validate_youtube_url("https://example.com")
        self.assertFalse(ok)


class TestParseMarkdownSections(unittest.TestCase):
    def test_basic_sections(self):
        md = "## Section A\nContent A\n## Section B\nContent B"
        sections = parse_markdown_sections(md)
        self.assertIn("Section A", sections)
        self.assertIn("Section B", sections)
        self.assertIn("Content A", sections["Section A"])

    def test_empty_markdown(self):
        sections = parse_markdown_sections("")
        self.assertEqual(sections, {})

    def test_no_sections(self):
        sections = parse_markdown_sections("Just plain text")
        self.assertEqual(sections, {})

    def test_h3_sections(self):
        md = "### Sub Section\nContent"
        sections = parse_markdown_sections(md)
        self.assertIn("Sub Section", sections)


class TestFormatDuration(unittest.TestCase):
    def test_seconds(self):
        self.assertIn("s", format_duration(45))

    def test_minutes(self):
        result = format_duration(90)
        self.assertIn("m", result)
        self.assertIn("1", result)

    def test_hours(self):
        result = format_duration(3660)
        self.assertIn("h", result)
        self.assertIn("1", result)

    def test_zero(self):
        self.assertIn("0", format_duration(0))


class TestCleanText(unittest.TestCase):
    def test_removes_music_tag(self):
        result = clean_text("Hello [Music] world")
        self.assertNotIn("[Music]", result)

    def test_removes_applause_tag(self):
        result = clean_text("Great [Applause] speech")
        self.assertNotIn("[Applause]", result)

    def test_collapses_whitespace(self):
        result = clean_text("hello   world\t\ttest")
        self.assertEqual(result, "hello world test")

    def test_strips_leading_trailing(self):
        result = clean_text("  hello  ")
        self.assertEqual(result, "hello")


# ─────────────────────────────────────────────────────────────
# models.py — test filter logic only (no network)
# ─────────────────────────────────────────────────────────────
from src.models import _is_text_model, FALLBACK_FREE_MODELS, FALLBACK_PAID_MODELS


class TestIsTextModel(unittest.TestCase):
    def _model(self, model_id, inputs, outputs):
        return {
            "id": model_id,
            "architecture": {
                "input_modalities": inputs,
                "output_modalities": outputs,
            },
        }

    def test_text_only_model_accepted(self):
        m = self._model("some/llm", ["text"], ["text"])
        self.assertTrue(_is_text_model(m))

    def test_audio_output_rejected(self):
        m = self._model("some/tts", ["text"], ["audio"])
        self.assertFalse(_is_text_model(m))

    def test_image_only_output_rejected(self):
        m = self._model("some/img-gen", ["text"], ["image"])
        self.assertFalse(_is_text_model(m))

    def test_no_text_input_rejected(self):
        m = self._model("some/vision", ["image"], ["text"])
        self.assertFalse(_is_text_model(m))

    def test_blocklist_keyword_rejected(self):
        m = self._model("some/ocr-model", ["text"], ["text"])
        self.assertFalse(_is_text_model(m))

    def test_vision_keyword_rejected(self):
        m = self._model("some/vision-model", ["text", "image"], ["text"])
        self.assertFalse(_is_text_model(m))

    def test_multimodal_text_in_out_accepted(self):
        # Model that accepts text+image but produces only text is fine
        m = self._model("some/multimodal", ["text", "image"], ["text"])
        self.assertTrue(_is_text_model(m))

    def test_fallback_models_are_valid_dicts(self):
        self.assertIsInstance(FALLBACK_FREE_MODELS, dict)
        self.assertGreater(len(FALLBACK_FREE_MODELS), 0)
        self.assertIsInstance(FALLBACK_PAID_MODELS, dict)


class TestFetchFreeModels(unittest.TestCase):
    def test_returns_fallback_on_network_error(self):
        from src.models import fetch_free_models
        with patch("requests.get", side_effect=Exception("network error")):
            result = fetch_free_models()
        self.assertEqual(result, FALLBACK_FREE_MODELS)

    def test_returns_fallback_on_empty_response(self):
        from src.models import fetch_free_models
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"data": []}
        with patch("requests.get", return_value=mock_resp):
            result = fetch_free_models()
        self.assertEqual(result, FALLBACK_FREE_MODELS)

    def test_filters_paid_models(self):
        from src.models import fetch_free_models
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "some/paid-model",
                    "pricing": {"prompt": "0.01", "completion": "0.02"},
                    "context_length": 32000,
                    "architecture": {
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                    },
                },
                {
                    "id": "some/free-model",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "context_length": 64000,
                    "architecture": {
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                    },
                },
            ]
        }
        with patch("requests.get", return_value=mock_resp):
            result = fetch_free_models()
        self.assertIn("some/free-model", result)
        self.assertNotIn("some/paid-model", result)


# ─────────────────────────────────────────────────────────────
# fusion.py
# ─────────────────────────────────────────────────────────────
from src.fusion import (
    merge_chapter_tables,
    select_top_insights,
    prepare_fusion_prompt,
)


class TestMergeChapterTables(unittest.TestCase):
    def test_single_list(self):
        chapters = [{"timestamp": "00:00", "title": "Intro"}]
        result = merge_chapter_tables([chapters])
        self.assertEqual(len(result), 1)

    def test_deduplication(self):
        a = [{"timestamp": "00:00"}, {"timestamp": "01:00"}]
        b = [{"timestamp": "00:00"}, {"timestamp": "02:00"}]
        result = merge_chapter_tables([a, b])
        timestamps = [c["timestamp"] for c in result]
        self.assertEqual(len(timestamps), len(set(timestamps)))

    def test_sorted_by_timestamp(self):
        a = [{"timestamp": "02:00"}]
        b = [{"timestamp": "00:00"}, {"timestamp": "01:00"}]
        result = merge_chapter_tables([a, b])
        self.assertEqual(result[0]["timestamp"], "00:00")

    def test_empty_lists(self):
        result = merge_chapter_tables([[], []])
        self.assertEqual(result, [])


class TestSelectTopInsights(unittest.TestCase):
    def test_returns_max_insights(self):
        lists = [["a", "b", "c"], ["d", "e", "f"]]
        result = select_top_insights(lists, max_insights=3)
        self.assertEqual(len(result), 3)

    def test_less_than_max(self):
        lists = [["a", "b"]]
        result = select_top_insights(lists, max_insights=5)
        self.assertEqual(len(result), 2)

    def test_empty(self):
        result = select_top_insights([[], []])
        self.assertEqual(result, [])


class TestPrepareFusionPrompt(unittest.TestCase):
    def test_prompt_contains_title_and_analyses(self):
        analyses = ["Analysis part 1", "Analysis part 2"]
        prompt = prepare_fusion_prompt(analyses, "My Video", "English")
        self.assertIn("My Video", prompt)
        self.assertIn("Analysis part 1", prompt)
        self.assertIn("Analysis part 2", prompt)

    def test_empty_analyses_filtered(self):
        analyses = ["Real analysis", "", None]
        prompt = prepare_fusion_prompt(analyses, "Title", "Français")
        self.assertIn("Real analysis", prompt)


# ─────────────────────────────────────────────────────────────
# _safe_format — analyzer & fusion
# ─────────────────────────────────────────────────────────────
from src.analyzer import _safe_format as analyzer_safe_format
from src.fusion import _safe_format as fusion_safe_format


class TestSafeFormat(unittest.TestCase):
    def test_basic_substitution(self):
        result = analyzer_safe_format("Hello {name}!", name="world")
        self.assertEqual(result, "Hello world!")

    def test_json_braces_not_tripped(self):
        tmpl = "Title: {title}\nContent: {transcript}"
        content_with_braces = '{"key": "value", "arr": [1, 2, 3]}'
        result = analyzer_safe_format(tmpl, title="Test", transcript=content_with_braces)
        self.assertIn('{"key": "value"', result)
        self.assertIn("Title: Test", result)

    def test_curly_braces_in_transcript_not_lost(self):
        tmpl = "{video_title}\n{transcript}"
        transcript = "He said {hello} and {{double}}"
        result = analyzer_safe_format(tmpl, video_title="V", transcript=transcript)
        self.assertIn("{hello}", result)
        self.assertIn("{{double}}", result)

    def test_multiple_placeholders(self):
        result = fusion_safe_format("{a} + {b} = {c}", a="1", b="2", c="3")
        self.assertEqual(result, "1 + 2 = 3")

    def test_missing_placeholder_left_unchanged(self):
        result = analyzer_safe_format("Hello {name} {other}!", name="world")
        self.assertIn("{other}", result)

    def test_output_language_substitution(self):
        tmpl = "Write in {output_language}. Title: {video_title}."
        result = analyzer_safe_format(tmpl, output_language="English", video_title="My Video")
        self.assertEqual(result, "Write in English. Title: My Video.")


# ─────────────────────────────────────────────────────────────
# extractor.py — 403 retry dict completeness
# ─────────────────────────────────────────────────────────────

class TestExtractorRetryDict(unittest.TestCase):
    """The 403 retry path must return all keys that process_url expects."""
    REQUIRED_KEYS = {"video_id", "transcript", "language", "title",
                     "total_duration_minutes", "entries_count"}

    def _make_formatted(self, n=3):
        return [{"text": f"seg {i}", "start": float(i * 10), "duration": 5.0} for i in range(n)]

    def test_retry_dict_has_all_required_keys(self):
        fmt = self._make_formatted()
        last = fmt[-1]
        total = last["start"] + last["duration"]
        result = {
            "video_id": "abc",
            "transcript": fmt,
            "language": "unknown",
            "title": "Test",
            "total_duration_minutes": total / 60,
            "entries_count": len(fmt),
        }
        missing = self.REQUIRED_KEYS - result.keys()
        self.assertEqual(missing, set(), f"Missing keys: {missing}")

    def test_empty_transcript_does_not_crash(self):
        fmt = []
        total = 0
        result = {
            "video_id": "abc",
            "transcript": fmt,
            "language": "unknown",
            "title": "Test",
            "total_duration_minutes": total / 60,
            "entries_count": len(fmt),
        }
        self.assertEqual(result["entries_count"], 0)
        self.assertEqual(result["total_duration_minutes"], 0.0)


# ─────────────────────────────────────────────────────────────
# config.py — MODEL_LIMITS removed, MODEL_CONTEXTS present
# ─────────────────────────────────────────────────────────────
import config as cfg


class TestConfig(unittest.TestCase):
    def test_model_contexts_exists(self):
        self.assertIsInstance(cfg.MODEL_CONTEXTS, dict)
        self.assertGreater(len(cfg.MODEL_CONTEXTS), 0)

    def test_model_limits_removed(self):
        self.assertFalse(hasattr(cfg, "MODEL_LIMITS"),
                         "MODEL_LIMITS should have been removed (duplicate of MODEL_CONTEXTS)")

    def test_get_model_context_limit_returns_int(self):
        limit = cfg.get_model_context_limit("meta-llama/llama-3.3-70b-instruct:free")
        self.assertIsInstance(limit, int)
        self.assertGreater(limit, 0)

    def test_unknown_model_returns_default(self):
        limit = cfg.get_model_context_limit("unknown/model-xyz")
        self.assertEqual(limit, 32000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
