import argparse
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

MODULE_PATH = pathlib.Path("/Users/zhaoshuai11/Desktop/fuck-skills/scripts/skills_router.py")
spec = importlib.util.spec_from_file_location("skills_router", MODULE_PATH)
skills_router = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = skills_router
spec.loader.exec_module(skills_router)


class SkillsRouterTests(unittest.TestCase):
    def test_parse_find_output_allows_url_on_following_line(self):
        output = """
warpdotdev/common-skills@review-pr 2.2K installs
└ https://skills.sh/warpdotdev/common-skills/review-pr
"""
        results = skills_router.parse_find_output(output)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["package"], "warpdotdev/common-skills@review-pr")
        self.assertEqual(results[0]["installs_value"], 2200)
        self.assertEqual(results[0]["url"], "https://skills.sh/warpdotdev/common-skills/review-pr")

    def test_validate_part_requires_queries_for_skill_parts(self):
        with self.assertRaises(RuntimeError):
            skills_router.validate_part(
                {"part_id": "p1", "title": "Review PR", "needs_skill": True, "queries": []},
                0,
            )

    def test_validate_part_normalizes_values(self):
        part = skills_router.validate_part(
            {
                "title": " Review PR ",
                "capability": " review ",
                "needs_skill": True,
                "queries": ["pr review", "pr review", " code review "],
            },
            0,
        )
        self.assertEqual(part["part_id"], "part-1")
        self.assertEqual(part["title"], "Review PR")
        self.assertEqual(part["capability"], "review")
        self.assertEqual(part["queries"], ["pr review", "code review"])

    def test_normalize_installed_item_derives_package_from_path(self):
        item = {"name": "review-pr", "path": "/tmp/skills/warpdotdev/common-skills/review-pr"}
        normalized = skills_router.normalize_installed_item(item)
        self.assertEqual(normalized["repo"], "warpdotdev/common-skills")
        self.assertEqual(normalized["skill"], "review-pr")
        self.assertEqual(normalized["package"], "warpdotdev/common-skills@review-pr")

    def test_summarize_plan_tracks_install_and_fallback(self):
        summary = skills_router.summarize_plan(
            [
                {
                    "part_id": "p1",
                    "selected": {"package": "owner/repo@skill-a"},
                    "fallback": False,
                    "reused": False,
                },
                {
                    "part_id": "p2",
                    "selected": {"package": "owner/repo@skill-a"},
                    "fallback": False,
                    "reused": True,
                },
                {
                    "part_id": "p3",
                    "selected": None,
                    "fallback": True,
                    "reused": False,
                },
            ]
        )
        self.assertEqual(summary["packages_to_install"], ["owner/repo@skill-a"])
        self.assertEqual(summary["reused_parts"], ["p2"])
        self.assertEqual(summary["fallback_parts"], ["p3"])

    def test_summarize_plan_tracks_already_installed_packages(self):
        summary = skills_router.summarize_plan(
            [
                {
                    "part_id": "p1",
                    "selected": {"package": "owner/repo@skill-a"},
                    "fallback": False,
                    "reused": False,
                },
                {
                    "part_id": "p2",
                    "selected": {"package": "owner/repo@skill-b"},
                    "fallback": False,
                    "reused": False,
                },
            ],
            installed_items=[{"package": "owner/repo@skill-a"}],
        )
        self.assertEqual(summary["already_installed_packages"], ["owner/repo@skill-a"])
        self.assertEqual(summary["packages_to_install"], ["owner/repo@skill-b"])

    def test_find_installed_by_package_matches_normalized_item(self):
        fake_items = [{"name": "review-pr", "path": "/tmp/skills/warpdotdev/common-skills/review-pr"}]
        with patch.object(skills_router, "list_installed", return_value=fake_items):
            result = skills_router.find_installed_by_package("warpdotdev/common-skills@review-pr")
        self.assertIsNotNone(result)
        self.assertEqual(result["package"], "warpdotdev/common-skills@review-pr")

    def test_resolve_installed_target_rejects_ambiguous_skill_name(self):
        fake_items = [
            {"name": "shared", "package": "owner-a/repo-a@shared", "repo": "owner-a/repo-a", "skill": "shared"},
            {"name": "shared", "package": "owner-b/repo-b@shared", "repo": "owner-b/repo-b", "skill": "shared"},
        ]
        with patch.object(skills_router, "list_installed", return_value=fake_items):
            with self.assertRaises(RuntimeError):
                skills_router.resolve_installed_target("shared")

    def test_run_check_returns_fail_on_nonzero_exit(self):
        completed = Mock(returncode=1, stdout="", stderr="boom")
        with patch.object(skills_router.subprocess, "run", return_value=completed):
            result = skills_router.run_check(["fake"], "help text", "fake")
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["help"], "help text")
        self.assertIn("boom", result["error"])

    def test_cmd_install_reports_package_field(self):
        args = argparse.Namespace(package="owner/repo@skill-a", json=True)
        installed = {"package": "owner/repo@skill-a", "path": "/tmp/skills/owner/repo/skill-a", "scope": "global", "agents": []}
        with patch.object(skills_router, "find_installed_by_package", side_effect=[None, installed]), \
             patch.object(skills_router, "skills_exec") as skills_exec, \
             patch.object(skills_router, "print_payload") as print_payload:
            skills_router.cmd_install(args)
        skills_exec.assert_called_once_with(["add", "owner/repo", "--skill", "skill-a", "-g", "-a", "codex", "-y"])
        payload = print_payload.call_args[0][0]
        self.assertEqual(payload["package"], "owner/repo@skill-a")
        self.assertFalse(payload["already_installed_before"])

    def test_cmd_remove_reports_cli_only_cleanup_mode(self):
        args = argparse.Namespace(skill_ref="owner/repo@skill-a", json=True)
        existing = {"package": "owner/repo@skill-a", "skill": "skill-a", "path": "/tmp/skills/owner/repo/skill-a"}
        with patch.object(skills_router, "resolve_installed_target", return_value=existing), \
             patch.object(skills_router, "skills_exec") as skills_exec, \
             patch.object(skills_router, "find_installed_by_package", return_value=None), \
             patch.object(skills_router, "print_payload") as print_payload:
            skills_router.cmd_remove(args)
        skills_exec.assert_called_once_with(["remove", "--global", "skill-a", "-y"])
        payload = print_payload.call_args[0][0]
        self.assertEqual(payload["cleanup_mode"], "cli_only")
        self.assertTrue(payload["removed"])

    def test_format_text_payload_for_checks(self):
        text = skills_router.format_text_payload(
            {"checks": [{"name": "node", "status": "ok", "version": "v1"}], "all_ok": True}
        )
        self.assertIn("[ok] node: v1", text)
        self.assertIn("all_ok=True", text)

    def test_format_text_payload_for_batch_summary(self):
        text = skills_router.format_text_payload(
            {
                "parts": [
                    {
                        "part_id": "p1",
                        "title": "Review PR",
                        "selected": {"package": "owner/repo@review", "relevance": "high", "relevance_score": 90},
                        "reused": False,
                    }
                ],
                "summary": {
                    "packages_to_install": ["owner/repo@review"],
                    "already_installed_packages": [],
                    "fallback_parts": [],
                    "reused_parts": [],
                },
            }
        )
        self.assertIn("p1: Review PR -> owner/repo@review [high:90]", text)
        self.assertIn("packages_to_install=owner/repo@review", text)

    def test_format_text_payload_for_search_query(self):
        text = skills_router.format_text_payload(
            {
                "query": "pr review",
                "results": [
                    {"package": "owner/repo@review", "installs_text": "2K", "matched_queries": ["pr review"]}
                ],
            }
        )
        self.assertIn("query=pr review", text)
        self.assertIn("owner/repo@review | 2K | queries=pr review", text)

    def test_format_text_payload_for_install_and_remove(self):
        install_text = skills_router.format_text_payload(
            {
                "package": "owner/repo@skill-a",
                "already_installed_before": False,
                "installed_path": "/tmp/skills/owner/repo/skill-a",
            }
        )
        remove_text = skills_router.format_text_payload(
            {"package": "owner/repo@skill-a", "removed": True, "cleanup_mode": "cli_only"}
        )
        self.assertIn("installed owner/repo@skill-a", install_text)
        self.assertIn("removed owner/repo@skill-a", remove_text)


if __name__ == "__main__":
    unittest.main()
