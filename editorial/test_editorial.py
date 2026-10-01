"""Failure-path checks for the independent editorial workflow."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, Mock

from editorial import editorial_pipeline as editor
from publishers import buffer_publisher as buffer

NEWS = [{"id": "source-1", "title": "AI workflow skills", "summary": "A practical workflow guide.", "source": "Example", "link": "https://example.com/skills"}]

class EditorialChecks(unittest.TestCase):
    def test_quota_timeout_and_malformed_ai_use_source_fallback(self):
        responses = [Mock(status_code=429, ok=False), Mock(status_code=503, ok=False), Mock(ok=True, status_code=200)]
        responses[-1].json.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not-json"}]}}]}
        failures = responses + [editor.requests.Timeout("secret-should-not-appear")]
        for failure in failures:
            kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with self.subTest(failure=type(failure).__name__), patch.object(editor, "GEMINI_KEY", "secret-should-not-appear"), patch.object(editor.requests, "post", **kwargs) as call:
                log = io.StringIO()
                with contextlib.redirect_stdout(log):
                    result, mode = editor.build_outputs(NEWS, [])
                self.assertEqual(mode, "fallback")
                self.assertIn("Source: Example", result["x_posts"][0]["text"])
                self.assertIn("Try:", result["x_posts"][0]["text"])
                self.assertNotIn("https://", json.dumps(result))
                self.assertNotIn("secret-should-not-appear", log.getvalue())
                self.assertEqual(call.call_count, 1)
                self.assertNotIn("key=", call.call_args.args[0])

    def test_valid_ai_normalizes_ids_and_rejects_unknown_sources(self):
        packet = {"newsletter_markdown": "A guide: " + NEWS[0]["link"], "x_posts": [{"source_id": "source-1", "text": "Read the guide: " + NEWS[0]["link"]}], "substack_notes": [{"source_id": "source-1", "text": "Try a small sample. " + NEWS[0]["link"]}]}
        normalized = editor.normalize_outputs(packet, NEWS, [])
        self.assertEqual(normalized["x_posts"][0]["id"], "x-source-1")
        packet["x_posts"][0]["text"] += " https://invented.example/job"
        with self.assertRaises(ValueError):
            editor.normalize_outputs(packet, NEWS, [])

    def test_telegram_pause_date_and_weekly_promotion(self):
        result = editor.fallback(NEWS, [])
        result["x_posts"][0]["text"] += "\nTelegram: https://t.me/VettedWeb3jobs"
        result = editor.apply_promotion(result, date(2026, 10, 1))
        self.assertNotIn("t.me", json.dumps(result))
        self.assertEqual(editor.cta(date(2026, 10, 14)), "")
        self.assertIn("Telegram", editor.cta(date(2026, 10, 15)))
        self.assertEqual(editor.cta(date(2026, 10, 16)), "")
        self.assertEqual(editor.strip_telegram("Advice\nhttps://t.me/other"), "Advice")

    def test_gemini_prose_receives_named_attribution_and_length_limit(self):
        packet = {"newsletter_markdown": "Career advice", "x_posts": [{"source_id": "source-1", "text": "🧑" * 300}], "substack_notes": [{"source_id": "source-1", "text": "Test one workflow and check the result."}]}
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(packet)}]}}]}
        with patch.object(editor, "GEMINI_KEY", "test-secret"), patch.object(editor.requests, "post", return_value=response), patch.object(editor, "cta", return_value=""):
            result, mode = editor.build_outputs(NEWS, [])
        self.assertEqual(mode, "gemini")
        self.assertLessEqual(editor.x_weight(result["x_posts"][0]["text"]), 280)
        for key in ("x_posts", "substack_notes"):
            self.assertTrue(result[key][0]["text"].endswith("Source: Example"))
            self.assertNotIn("https://", result[key][0]["text"])

    def test_article_extraction_ignores_page_chrome_and_falls_back_on_failure(self):
        paragraph = "A developer survey compares AI use, work practices and community demographics across two years. "
        html = "<nav>Ignore navigation</nav><article><p>" + paragraph * 4 + "</p><aside><p>Ignore advertising</p></aside></article>"
        extracted = editor.article_excerpt(html)
        self.assertIn("developer survey", extracted)
        self.assertNotIn("Ignore", extracted)
        self.assertEqual(editor.article_excerpt("<article><p>Sign in</p></article>"), "")
        sources = [{"url": "https://example.com/feed"}]
        with patch.object(editor, "load_json", return_value=sources), patch.object(editor.requests, "get", side_effect=editor.requests.Timeout):
            result = editor.enrich_news(copy.deepcopy(NEWS))
        self.assertEqual(result[0]["evidence"], "rss")
        self.assertEqual(result[0]["summary"], NEWS[0]["summary"])

    def test_markdown_links_are_removed_but_attribution_and_facts_remain(self):
        packet = {"newsletter_markdown": "A [guide](" + NEWS[0]["link"] + ")", "x_posts": [{"source_id": "source-1", "text": "Workflow advice " + NEWS[0]["link"]}], "substack_notes": [{"source_id": "source-1", "text": "Try one task. Source: " + NEWS[0]["link"]}]}
        result = editor.normalize_outputs(packet, NEWS, [])
        self.assertNotIn("https://", json.dumps(result))
        self.assertIn("Workflow advice", result["x_posts"][0]["text"])
        self.assertIn("Sources: Example", result["newsletter_markdown"])

    def test_publisher_records_one_promotion_and_deduplicates(self):
        rows = [{"id": f"post-{i}", "text": "Advice\nCheck out our Telegram: https://t.me/VettedWeb3jobs", "promotion_week": "2026-W42"} for i in range(2)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            path.write_text(json.dumps(rows))
            state = {}
            with patch.object(buffer, "STATE", Path(folder) / "state.json"), patch.object(buffer, "SAVE_AS_DRAFT", True), patch.object(buffer, "create_post", return_value={"id": "confirmed"}) as create:
                buffer.publish_queue(path, "x", "channel", 2, state)
                self.assertIn("Telegram", create.call_args_list[0].args[1])
                self.assertNotIn("Telegram", create.call_args_list[1].args[1])
                buffer.publish_queue(path, "x", "channel", 2, state)
                self.assertEqual(create.call_count, 2)

    def test_source_freshness_and_x_budget(self):
        self.assertIsNone(editor.entry_time(Mock(published_parsed=None, updated_parsed=None)))
        self.assertFalse(editor.career_relevant("Kindle remote control", "A button for your reader."))
        self.assertFalse(editor.career_relevant("Amazon introduces Kindle Click, a $35 remote for turning pages", "The compact Bluetooth remote is designed to let readers turn pages."))
        post = editor.fit_x("Emoji: " + "🧑" * 300, NEWS[0]["link"])
        self.assertLessEqual(editor.x_weight(post), 280)
        self.assertTrue(post.endswith(NEWS[0]["link"]))

if __name__ == "__main__":
    unittest.main()
