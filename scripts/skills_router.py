#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "for",
    "of",
    "in",
    "on",
    "with",
    "by",
    "from",
    "best",
    "practices",
    "workflow",
    "task",
    "part",
}


def run_cmd(cmd: List[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Command failed: {' '.join(cmd)}")
    return result.stdout



def skills_exec(args: List[str]) -> str:
    cmd = ["npm", "exec", "--yes", "--package=skills", "--", "skills", *args]
    return run_cmd(cmd)



def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)



def parse_install_count(text: str) -> int:
    value = (text or "").strip().upper()
    if not value:
        return 0

    multiplier = 1
    if value.endswith("K"):
        multiplier = 1000
        value = value[:-1]
    elif value.endswith("M"):
        multiplier = 1000000
        value = value[:-1]
    elif value.endswith("B"):
        multiplier = 1000000000
        value = value[:-1]

    try:
        return int(float(value) * multiplier)
    except ValueError:
        return 0



def tokenize(text: str) -> List[str]:
    tokens = TOKEN_RE.findall((text or "").lower())
    return [token for token in tokens if token not in STOPWORDS]



def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result



def parse_find_output(output: str) -> List[Dict[str, Any]]:
    clean_output = strip_ansi(output)
    lines = [line.rstrip() for line in clean_output.splitlines() if line.strip()]
    results: List[Dict[str, Any]] = []
    i = 0
    pattern = re.compile(r"^(?P<pkg>[^\s]+@[^\s]+)\s+(?P<installs>[\d.]+[KMB]?)\s+installs$")

    while i < len(lines):
        line = lines[i].strip()
        match = pattern.match(line)
        if match:
            package_ref = match.group("pkg")
            repo, skill = package_ref.rsplit("@", 1)
            installs_text = match.group("installs")
            url = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("└ https://skills.sh/"):
                    url = next_line.replace("└ ", "", 1)
                    i += 1

            results.append(
                {
                    "package": package_ref,
                    "repo": repo,
                    "skill": skill,
                    "installs_text": installs_text,
                    "installs_value": parse_install_count(installs_text),
                    "url": url,
                }
            )
        i += 1

    return results



def search_query(query: str) -> Dict[str, Any]:
    output = skills_exec(["find", query])
    candidates = parse_find_output(output)
    for candidate in candidates:
        candidate["matched_queries"] = [query]
    return {"query": query, "results": candidates}



def merge_candidates(search_payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for payload in search_payloads:
        query = payload["query"]
        for candidate in payload["results"]:
            package = candidate["package"]
            if package not in merged:
                merged[package] = {
                    "package": candidate["package"],
                    "repo": candidate["repo"],
                    "skill": candidate["skill"],
                    "installs_text": candidate["installs_text"],
                    "installs_value": candidate["installs_value"],
                    "url": candidate.get("url", ""),
                    "matched_queries": [query],
                }
            else:
                merged[package]["matched_queries"].append(query)
                if candidate["installs_value"] > merged[package]["installs_value"]:
                    merged[package]["installs_value"] = candidate["installs_value"]
                    merged[package]["installs_text"] = candidate["installs_text"]
                if candidate.get("url") and not merged[package].get("url"):
                    merged[package]["url"] = candidate["url"]

    result = list(merged.values())
    for item in result:
        item["matched_queries"] = unique_keep_order(item["matched_queries"])
    return result



def build_part_context(part_title: str, capability: str, queries: List[str]) -> str:
    pieces = [part_title or "", capability or "", " ".join(queries)]
    return " ".join(piece for piece in pieces if piece).strip()



def score_candidate(part_title: str, capability: str, queries: List[str], candidate: Dict[str, Any]) -> Dict[str, Any]:
    candidate_text = " ".join(
        [
            candidate.get("package", ""),
            candidate.get("repo", ""),
            candidate.get("skill", ""),
            candidate.get("url", ""),
        ]
    ).lower()

    part_tokens = set(tokenize(build_part_context(part_title, capability, queries)))
    candidate_tokens = set(tokenize(candidate_text))
    overlap = part_tokens & candidate_tokens

    score = len(overlap) * 10
    exact_matches = []

    for query in queries:
        query_norm = " ".join(tokenize(query))
        if query_norm and query_norm in candidate_text:
            exact_matches.append(query)
            score += 60

    if capability:
        cap_norm = " ".join(tokenize(capability))
        if cap_norm and cap_norm in candidate_text:
            score += 25

    part_norm = " ".join(tokenize(part_title))
    if part_norm and part_norm in candidate_text:
        score += 35

    if candidate.get("skill", "") in (part_title or ""):
        score += 10

    if score >= 80:
        relevance = "high"
    elif score >= 30:
        relevance = "medium"
    elif score > 0:
        relevance = "low"
    else:
        relevance = "none"

    return {
        "relevance_score": score,
        "relevance": relevance,
        "overlap_tokens": sorted(overlap),
        "exact_query_matches": exact_matches,
    }



def rank_candidates(part_title: str, capability: str, queries: List[str], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    for candidate in candidates:
        scored = dict(candidate)
        scored.update(score_candidate(part_title, capability, queries, candidate))
        ranked.append(scored)

    ranked.sort(key=lambda item: (item["relevance_score"], item["installs_value"]), reverse=True)
    return ranked



def filter_relevant_candidates(ranked_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    high_or_medium = [item for item in ranked_candidates if item["relevance"] in ("high", "medium")]
    if high_or_medium:
        return high_or_medium

    low = [item for item in ranked_candidates if item["relevance"] == "low"]
    if low:
        return low

    return ranked_candidates



def select_for_part(part: Dict[str, Any]) -> Dict[str, Any]:
    part_id = part.get("part_id") or part.get("id") or part.get("title") or "part"
    title = part.get("title", "")
    capability = part.get("capability", "")
    queries = unique_keep_order(part.get("queries", []))
    needs_skill = bool(part.get("needs_skill", True))

    if not needs_skill:
        return {
            "part_id": part_id,
            "title": title,
            "capability": capability,
            "needs_skill": False,
            "selected": None,
            "fallback": True,
            "reason": "Part does not require an external skill",
            "queries": queries,
            "candidates": [],
        }

    if not queries:
        raise RuntimeError(f"Part '{part_id}' has no queries")

    search_payloads = [search_query(query) for query in queries]
    merged_candidates = merge_candidates(search_payloads)
    ranked_candidates = rank_candidates(title, capability, queries, merged_candidates)
    relevant_candidates = filter_relevant_candidates(ranked_candidates)
    selected = relevant_candidates[0] if relevant_candidates else None

    return {
        "part_id": part_id,
        "title": title,
        "capability": capability,
        "needs_skill": True,
        "queries": queries,
        "searches": search_payloads,
        "candidates": relevant_candidates,
        "all_candidates": ranked_candidates,
        "selected": selected,
        "fallback": selected is None,
        "reason": None if selected else "No strong relevant skill candidate found",
    }



def reuse_or_select(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    selections = []
    chosen_registry: Dict[str, Dict[str, Any]] = {}

    for part in parts:
        selection = select_for_part(part)
        selected = selection.get("selected")

        if selection.get("fallback") or not selected:
            selections.append(selection)
            continue

        title = selection.get("title", "")
        capability = selection.get("capability", "")
        queries = selection.get("queries", [])
        top_score = selected.get("relevance_score", 0)
        reuse_choice = None

        for package, existing in chosen_registry.items():
            existing_scored = dict(existing)
            existing_scored.update(score_candidate(title, capability, queries, existing))
            if existing_scored.get("relevance_score", 0) >= top_score and existing_scored.get("relevance_score", 0) > 0:
                if reuse_choice is None or existing_scored["relevance_score"] > reuse_choice["relevance_score"]:
                    reuse_choice = existing_scored

        if reuse_choice is not None:
            selection["selected"] = reuse_choice
            selection["reused"] = True
            selection["reused_from_package"] = reuse_choice["package"]
            selection["selection_reason"] = "Reused a previously selected skill with equal or better relevance"
        else:
            selection["reused"] = False
            selection["reused_from_package"] = None
            selection["selection_reason"] = "Highest-install relevant skill for this part"
            chosen_registry[selected["package"]] = selected

        selections.append(selection)

    return {"parts": selections}



def list_installed() -> List[Dict[str, Any]]:
    output = skills_exec(["ls", "-g", "-a", "codex", "--json"])
    return json.loads(output)



def find_installed_skill(skill_name: str) -> Optional[Dict[str, Any]]:
    for item in list_installed():
        if item.get("name") == skill_name:
            return item
    return None



def load_parts_from_args(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.parts_file:
        return json.loads(Path(args.parts_file).read_text())
    if args.parts_json:
        return json.loads(args.parts_json)
    raise RuntimeError("Provide --parts-file or --parts-json")



def print_payload(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if isinstance(payload, str):
            print(payload)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))



def cmd_search(args: argparse.Namespace) -> None:
    payload = search_query(args.query)
    print_payload(payload, args.json)



def cmd_search_many(args: argparse.Namespace) -> None:
    queries = unique_keep_order(args.query)
    if not queries:
        raise RuntimeError("Provide at least one --query")

    search_payloads = [search_query(query) for query in queries]
    merged = merge_candidates(search_payloads)
    merged.sort(key=lambda item: item["installs_value"], reverse=True)
    payload = {"queries": queries, "searches": search_payloads, "results": merged}
    print_payload(payload, args.json)



def cmd_select(args: argparse.Namespace) -> None:
    part = {
        "part_id": args.part_id or args.part_title or "part-1",
        "title": args.part_title,
        "capability": args.capability or "",
        "queries": unique_keep_order(args.query),
        "needs_skill": True,
    }
    payload = select_for_part(part)
    print_payload(payload, args.json)



def cmd_batch_select(args: argparse.Namespace) -> None:
    parts = load_parts_from_args(args)
    payload = reuse_or_select(parts)
    print_payload(payload, args.json)



def cmd_install(args: argparse.Namespace) -> None:
    if "@" not in args.package:
        raise RuntimeError("package must look like owner/repo@skill-name")

    repo, skill_name = args.package.rsplit("@", 1)
    existing = find_installed_skill(skill_name)
    already_installed_before = existing is not None

    if not already_installed_before:
        skills_exec(["add", repo, "--skill", skill_name, "-g", "-a", "codex", "-y"])

    installed = find_installed_skill(skill_name)
    if not installed:
        raise RuntimeError(f"Installed skill '{skill_name}' was not found in Codex global skills")

    payload = {
        "repo": repo,
        "skill": skill_name,
        "already_installed_before": already_installed_before,
        "installed_path": installed.get("path"),
        "scope": installed.get("scope"),
        "agents": installed.get("agents", []),
    }
    print_payload(payload, args.json)



def cmd_remove(args: argparse.Namespace) -> None:
    existing = find_installed_skill(args.skill_name)
    removed = False
    path = existing.get("path") if existing else None

    if existing:
        skills_exec(["remove", "--global", args.skill_name, "-y"])
        removed = True
        remaining = find_installed_skill(args.skill_name)
        if remaining:
            remaining_path = Path(remaining.get("path", ""))
            if remaining_path.exists() and remaining_path.is_symlink():
                remaining_path.unlink()

    if path:
        p = Path(path)
        if p.exists() and not p.is_symlink():
            shutil.rmtree(p)

    payload = {"skill": args.skill_name, "removed": removed, "path": path}
    print_payload(payload, args.json)



def cmd_list(args: argparse.Namespace) -> None:
    payload = list_installed()
    print_payload(payload, args.json)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Temporary external skill router helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_search_many = sub.add_parser("search-many")
    p_search_many.add_argument("--query", action="append", required=True)
    p_search_many.add_argument("--json", action="store_true")
    p_search_many.set_defaults(func=cmd_search_many)

    p_select = sub.add_parser("select")
    p_select.add_argument("--part-id")
    p_select.add_argument("--part-title", required=True)
    p_select.add_argument("--capability")
    p_select.add_argument("--query", action="append", required=True)
    p_select.add_argument("--json", action="store_true")
    p_select.set_defaults(func=cmd_select)

    p_batch = sub.add_parser("batch-select")
    p_batch.add_argument("--parts-file")
    p_batch.add_argument("--parts-json")
    p_batch.add_argument("--json", action="store_true")
    p_batch.set_defaults(func=cmd_batch_select)

    p_install = sub.add_parser("install")
    p_install.add_argument("package")
    p_install.add_argument("--json", action="store_true")
    p_install.set_defaults(func=cmd_install)

    p_remove = sub.add_parser("remove")
    p_remove.add_argument("skill_name")
    p_remove.add_argument("--json", action="store_true")
    p_remove.set_defaults(func=cmd_remove)

    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
