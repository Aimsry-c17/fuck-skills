#!/usr/bin/env python3
import argparse
import json
import re
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


def run_cmd(cmd: List[str], timeout: int = 60, retries: int = 2) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Command failed: {' '.join(cmd)}")
            return result.stdout
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from e
        except RuntimeError as e:
            last_error = e
            if attempt < retries - 1:
                print(f"Retrying ({attempt + 1}/{retries - 1})...", file=sys.stderr)
    raise RuntimeError(str(last_error))



def skills_exec(args: List[str]) -> str:
    cmd = ["npm", "exec", "--yes", "--package=skills", "--", "skills", *args]
    return run_cmd(cmd, timeout=180, retries=2)



def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)



def parse_install_count(text: str) -> int:
    value = (text or "").strip().upper().replace(",", "")
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
    current: Optional[Dict[str, Any]] = None
    pattern = re.compile(r"^(?P<pkg>[^\s]+@[^\s]+)\s+(?P<installs>[\d.,]+(?:[KMBkmb])?)\s+installs(?:\s|$)")

    for raw_line in lines:
        line = raw_line.strip()
        match = pattern.match(line)
        if match:
            if current is not None:
                results.append(current)
            package_ref = match.group("pkg")
            repo, skill = package_ref.rsplit("@", 1)
            installs_text = match.group("installs")
            current = {
                "package": package_ref,
                "repo": repo,
                "skill": skill,
                "installs_text": installs_text,
                "installs_value": parse_install_count(installs_text),
                "url": "",
            }
            continue

        if current is not None and not current.get("url"):
            url_match = re.search(r"https://skills\.sh/\S+", line)
            if url_match:
                current["url"] = url_match.group(0)

    if current is not None:
        results.append(current)

    return results



def search_query(query: str) -> Dict[str, Any]:
    print(f"Searching skills.sh for: {query}", file=sys.stderr)
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



def score_candidate(
    part_title: str,
    capability: str,
    queries: List[str],
    candidate: Dict[str, Any],
    high_threshold: int = 80,
    medium_threshold: int = 30,
) -> Dict[str, Any]:
    package_text = (candidate.get("package", "") or "").lower()
    repo_text = (candidate.get("repo", "") or "").lower()
    skill_text = (candidate.get("skill", "") or "").lower()
    url_text = (candidate.get("url", "") or "").lower()
    candidate_text = " ".join([package_text, repo_text, skill_text, url_text]).strip()

    part_tokens = set(tokenize(build_part_context(part_title, capability, queries)))
    repo_tokens = set(tokenize(repo_text))
    skill_tokens = set(tokenize(skill_text))
    url_tokens = set(tokenize(url_text))
    candidate_tokens = repo_tokens | skill_tokens | url_tokens
    overlap = part_tokens & candidate_tokens

    token_score = len(overlap & skill_tokens) * 12 + len(overlap & repo_tokens) * 6 + len(overlap & url_tokens) * 3
    exact_matches = []
    exact_score = 0

    for query in queries:
        query_tokens = tokenize(query)
        query_norm = " ".join(query_tokens)
        if not query_norm:
            continue
        if query_norm in skill_text or query_norm in repo_text:
            exact_matches.append(query)
            exact_score += 40
        elif set(query_tokens) and set(query_tokens).issubset(skill_tokens | repo_tokens):
            exact_matches.append(query)
            exact_score += 25

    cap_score = 0
    cap_tokens = set(tokenize(capability))
    if cap_tokens and cap_tokens & (skill_tokens | repo_tokens):
        cap_score = 20

    title_score = 0
    title_tokens = set(tokenize(part_title))
    if title_tokens and title_tokens & skill_tokens:
        title_score = 25
    elif title_tokens and title_tokens & repo_tokens:
        title_score = 10

    name_score = 0
    if title_tokens and skill_tokens and title_tokens & skill_tokens:
        name_score = 10

    score = token_score + exact_score + cap_score + title_score + name_score

    if score >= high_threshold:
        relevance = "high"
    elif score >= medium_threshold:
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
        "score_breakdown": {
            "token_overlap": token_score,
            "token_count": len(overlap),
            "overlap_tokens": sorted(overlap),
            "exact_query_match": exact_score,
            "exact_matches": exact_matches,
            "capability_match": cap_score,
            "title_match": title_score,
            "skill_name_match": name_score,
            "total": score,
        },
    }



def rank_candidates(
    part_title: str,
    capability: str,
    queries: List[str],
    candidates: List[Dict[str, Any]],
    high_threshold: int = 80,
    medium_threshold: int = 30,
) -> List[Dict[str, Any]]:
    ranked = []
    for candidate in candidates:
        scored = dict(candidate)
        scored.update(score_candidate(part_title, capability, queries, candidate, high_threshold, medium_threshold))
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

    return []



def select_for_part(
    part: Dict[str, Any],
    high_threshold: int = 80,
    medium_threshold: int = 30,
) -> Dict[str, Any]:
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
    ranked_candidates = rank_candidates(title, capability, queries, merged_candidates, high_threshold, medium_threshold)
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



def reuse_or_select(
    parts: List[Dict[str, Any]],
    high_threshold: int = 80,
    medium_threshold: int = 30,
) -> Dict[str, Any]:
    selections = []
    chosen_registry: Dict[str, Dict[str, Any]] = {}

    for part in parts:
        selection = select_for_part(part, high_threshold, medium_threshold)
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
            existing_scored.update(
                score_candidate(title, capability, queries, existing, high_threshold, medium_threshold)
            )
            existing_score = existing_scored.get("relevance_score", 0)
            exact_matches = existing_scored.get("exact_query_matches", [])
            has_strong_signal = bool(exact_matches) or existing_scored.get("score_breakdown", {}).get("capability_match", 0) > 0
            if (
                existing_score >= top_score
                and existing_score >= medium_threshold
                and has_strong_signal
            ):
                if reuse_choice is None or existing_score > reuse_choice["relevance_score"]:
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



def split_package_ref(package: str) -> Tuple[str, str]:
    if "@" not in package:
        raise RuntimeError("package must look like owner/repo@skill-name")
    return package.rsplit("@", 1)



def normalize_installed_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item)
    repo = item.get("repo") or item.get("owner_repo")
    skill_name = item.get("name") or item.get("skill")
    package = item.get("package")

    path = item.get("path") or ""
    if (not repo or not package) and path:
        resolved = Path(path)
        parts = resolved.parts
        if "skills" in parts:
            idx = parts.index("skills")
            if idx + 2 < len(parts):
                repo = repo or f"{parts[idx + 1]}/{parts[idx + 2]}"
                if idx + 3 < len(parts):
                    skill_name = skill_name or parts[idx + 3]
        elif ".skills" in parts:
            idx = parts.index(".skills")
            if idx + 2 < len(parts):
                repo = repo or f"{parts[idx + 1]}/{parts[idx + 2]}"
                if idx + 3 < len(parts):
                    skill_name = skill_name or parts[idx + 3]

    if repo and skill_name and not package:
        package = f"{repo}@{skill_name}"

    normalized["repo"] = repo
    normalized["skill"] = skill_name
    normalized["package"] = package
    return normalized



def list_installed() -> List[Dict[str, Any]]:
    output = skills_exec(["ls", "-g", "-a", "codex", "--json"])
    return json.loads(output)



def find_installed_by_package(package: str) -> Optional[Dict[str, Any]]:
    repo, skill_name = split_package_ref(package)
    skill_name_matches: List[Dict[str, Any]] = []
    for item in list_installed():
        normalized = normalize_installed_item(item)
        if normalized.get("package") == package:
            return normalized
        if normalized.get("repo") == repo and normalized.get("skill") == skill_name:
            return normalized
        if normalized.get("skill") == skill_name or normalized.get("name") == skill_name:
            skill_name_matches.append(normalized)

    if len(skill_name_matches) == 1:
        return skill_name_matches[0]
    return None



def find_installed_by_skill_name(skill_name: str) -> List[Dict[str, Any]]:
    matches = []
    for item in list_installed():
        normalized = normalize_installed_item(item)
        if normalized.get("name") == skill_name or normalized.get("skill") == skill_name:
            matches.append(normalized)
    return matches



def resolve_installed_target(identifier: str) -> Dict[str, Any]:
    if "@" in identifier:
        existing = find_installed_by_package(identifier)
        if existing is None:
            raise RuntimeError(f"Installed skill '{identifier}' was not found")
        return existing

    matches = find_installed_by_skill_name(identifier)
    if not matches:
        raise RuntimeError(f"Installed skill '{identifier}' was not found")
    if len(matches) > 1:
        packages = [item.get("package") or item.get("name") for item in matches]
        raise RuntimeError(
            "Ambiguous installed skill name. Use owner/repo@skill-name instead: " + ", ".join(packages)
        )
    return matches[0]



def validate_part(part: Dict[str, Any], index: int) -> Dict[str, Any]:
    normalized = dict(part)
    part_id = normalized.get("part_id") or normalized.get("id") or f"part-{index + 1}"
    title = normalized.get("title")
    capability = normalized.get("capability") or ""
    needs_skill = normalized.get("needs_skill", True)
    queries = normalized.get("queries", [])

    if not isinstance(title, str) or not title.strip():
        raise RuntimeError(f"Part '{part_id}' must include a non-empty title")
    if not isinstance(capability, str):
        raise RuntimeError(f"Part '{part_id}' capability must be a string")
    if not isinstance(needs_skill, bool):
        raise RuntimeError(f"Part '{part_id}' needs_skill must be a boolean")
    if not isinstance(queries, list) or any(not isinstance(query, str) or not query.strip() for query in queries):
        raise RuntimeError(f"Part '{part_id}' queries must be a list of non-empty strings")
    if needs_skill and not queries:
        raise RuntimeError(f"Part '{part_id}' has no queries")

    normalized["part_id"] = part_id
    normalized["title"] = title.strip()
    normalized["capability"] = capability.strip()
    normalized["needs_skill"] = needs_skill
    normalized["queries"] = unique_keep_order([query.strip() for query in queries])
    return normalized



def summarize_plan(parts: List[Dict[str, Any]], installed_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    packages_to_install = []
    already_installed_packages = []
    fallback_parts = []
    reused_parts = []
    installed_packages = {
        item.get("package")
        for item in (installed_items or [])
        if item.get("package")
    }

    for part in parts:
        selected = part.get("selected")
        if part.get("fallback") or not selected:
            fallback_parts.append(part.get("part_id"))
            continue
        if part.get("reused"):
            reused_parts.append(part.get("part_id"))
            continue
        package = selected.get("package")
        if not package:
            continue
        if package in installed_packages:
            if package not in already_installed_packages:
                already_installed_packages.append(package)
        elif package not in packages_to_install:
            packages_to_install.append(package)

    return {
        "parts_total": len(parts),
        "packages_to_install": packages_to_install,
        "already_installed_packages": already_installed_packages,
        "fallback_parts": fallback_parts,
        "reused_parts": reused_parts,
    }



def load_parts_from_args(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.parts_file:
        parts = json.loads(Path(args.parts_file).read_text(encoding="utf-8"))
    elif args.parts_json:
        parts = json.loads(args.parts_json)
    else:
        raise RuntimeError("Provide --parts-file or --parts-json")

    if not isinstance(parts, list):
        raise RuntimeError("Parts input must be a JSON array")

    return [validate_part(part, index) for index, part in enumerate(parts)]



def format_text_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload

    if isinstance(payload, list):
        if not payload:
            return "(empty)"
        lines = []
        for item in payload:
            if isinstance(item, dict):
                package = item.get("package") or item.get("name") or item.get("skill") or "item"
                path = item.get("path")
                scope = item.get("scope")
                line = package
                extras = [value for value in [scope, path] if value]
                if extras:
                    line += " | " + " | ".join(extras)
                lines.append(line)
            else:
                lines.append(str(item))
        return "\n".join(lines)

    if not isinstance(payload, dict):
        return str(payload)

    if "checks" in payload:
        lines = []
        for check in payload.get("checks", []):
            if check.get("status") == "ok":
                lines.append(f"[ok] {check.get('name')}: {check.get('version', '')}".rstrip())
            else:
                lines.append(f"[fail] {check.get('name')}: {check.get('error', '')}".rstrip())
        lines.append(f"all_ok={payload.get('all_ok')}")
        return "\n".join(lines)

    if "parts" in payload and isinstance(payload.get("parts"), list):
        lines = []
        for part in payload["parts"]:
            selected = part.get("selected")
            if selected:
                lines.append(
                    f"{part.get('part_id')}: {part.get('title')} -> {selected.get('package')} "
                    f"[{selected.get('relevance')}:{selected.get('relevance_score')}]"
                    + (" (reused)" if part.get("reused") else "")
                )
            else:
                lines.append(f"{part.get('part_id')}: {part.get('title')} -> fallback")
        summary = payload.get("summary")
        if isinstance(summary, dict):
            lines.append(f"packages_to_install={', '.join(summary.get('packages_to_install', [])) or '-'}")
            lines.append(f"already_installed_packages={', '.join(summary.get('already_installed_packages', [])) or '-'}")
            lines.append(f"fallback_parts={', '.join(summary.get('fallback_parts', [])) or '-'}")
            lines.append(f"reused_parts={', '.join(summary.get('reused_parts', [])) or '-'}")
        return "\n".join(lines)

    if "query" in payload and "results" in payload and isinstance(payload.get("results"), list):
        lines = [f"query={payload.get('query')}"]
        if payload["results"]:
            lines.extend(
                f"{item.get('package')} | {item.get('installs_text')} | queries={','.join(item.get('matched_queries', []))}"
                for item in payload["results"]
            )
        else:
            lines.append("(empty)")
        return "\n".join(lines)

    if "results" in payload and isinstance(payload.get("results"), list):
        return "\n".join(
            f"{item.get('package')} | {item.get('installs_text')} | queries={','.join(item.get('matched_queries', []))}"
            for item in payload["results"]
        ) or "(empty)"

    if "selected" in payload or "fallback" in payload:
        selected = payload.get("selected")
        if selected:
            return (
                f"{payload.get('part_id')}: {payload.get('title')} -> {selected.get('package')} "
                f"[{selected.get('relevance')}:{selected.get('relevance_score')}]"
            )
        return f"{payload.get('part_id')}: {payload.get('title')} -> fallback"

    if "package" in payload and "already_installed_before" in payload:
        return (
            f"installed {payload.get('package')} | already_installed_before={payload.get('already_installed_before')} "
            f"| path={payload.get('installed_path') or '-'}"
        )

    if "removed" in payload and "package" in payload:
        return f"removed {payload.get('package')} | removed={payload.get('removed')} | mode={payload.get('cleanup_mode')}"

    return json.dumps(payload, ensure_ascii=False, indent=2)



def print_payload(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_text_payload(payload))



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
    payload = select_for_part(part, args.relevance_high, args.relevance_medium)
    print_payload(payload, args.json)



def cmd_batch_select(args: argparse.Namespace) -> None:
    parts = load_parts_from_args(args)
    payload = reuse_or_select(parts, args.relevance_high, args.relevance_medium)
    installed_items = [normalize_installed_item(item) for item in list_installed()]
    payload["summary"] = summarize_plan(payload.get("parts", []), installed_items)
    if args.dry_run:
        payload["mode"] = "dry_run"
        payload["message"] = "Dry run — no skills will be installed. Review the plan below."
    print_payload(payload, args.json)



def cmd_install(args: argparse.Namespace) -> None:
    repo, skill_name = split_package_ref(args.package)
    existing = find_installed_by_package(args.package)
    already_installed_before = existing is not None

    if not already_installed_before:
        skills_exec(["add", repo, "--skill", skill_name, "-g", "-a", "codex", "-y"])

    installed = find_installed_by_package(args.package)
    if not installed:
        raise RuntimeError(f"Installed skill '{args.package}' was not found in Codex global skills")

    payload = {
        "package": args.package,
        "repo": repo,
        "skill": skill_name,
        "already_installed_before": already_installed_before,
        "installed_path": installed.get("path"),
        "scope": installed.get("scope"),
        "agents": installed.get("agents", []),
    }
    print_payload(payload, args.json)



def cmd_remove(args: argparse.Namespace) -> None:
    existing = resolve_installed_target(args.skill_ref)
    target_identifier = existing.get("package") or args.skill_ref
    path = existing.get("path")
    skill_name = existing.get("skill") or existing.get("name") or args.skill_ref

    skills_exec(["remove", "--global", skill_name, "-y"])

    removed = False
    if "@" in args.skill_ref:
        removed = find_installed_by_package(args.skill_ref) is None
    else:
        removed = len(find_installed_by_skill_name(skill_name)) == 0

    payload = {
        "skill": skill_name,
        "package": target_identifier,
        "removed": removed,
        "path": path,
        "cleanup_mode": "cli_only",
    }
    print_payload(payload, args.json)



def cmd_list(args: argparse.Namespace) -> None:
    payload = list_installed()
    print_payload(payload, args.json)


def run_check(cmd: List[str], help_text: str, name: str) -> Dict[str, Any]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        return {"name": name, "status": "fail", "error": str(e), "help": help_text}

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        return {
            "name": name,
            "status": "fail",
            "error": stderr or stdout or f"Command failed with exit code {result.returncode}",
            "help": help_text,
        }

    return {"name": name, "status": "ok", "version": stdout or stderr}



def cmd_check(args: argparse.Namespace) -> None:
    results: Dict[str, Any] = {"checks": []}

    checks_to_run: List[Dict[str, Any]] = [
        {
            "name": "node",
            "cmd": ["node", "--version"],
            "help": "Install Node.js from https://nodejs.org (LTS recommended)",
        },
        {
            "name": "npm",
            "cmd": ["npm", "--version"],
            "help": "npm is bundled with Node.js",
        },
        {
            "name": "skills",
            "cmd": ["npm", "exec", "--yes", "--package=skills", "--", "skills", "--version"],
            "help": "The skills CLI is fetched on-demand; check your network connection",
        },
        {
            "name": "python3",
            "cmd": ["python3", "--version"],
            "help": "Python 3 is required to run this helper script",
        },
    ]

    for check in checks_to_run:
        print(f"Checking {check['name']}...", file=sys.stderr)
        results["checks"].append(run_check(check["cmd"], check["help"], check["name"]))

    results["all_ok"] = all(c["status"] == "ok" for c in results["checks"])
    print_payload(results, args.json)



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
    p_select.add_argument("--relevance-high", type=int, default=80, help="Score threshold for high relevance (default: 80)")
    p_select.add_argument("--relevance-medium", type=int, default=30, help="Score threshold for medium relevance (default: 30)")
    p_select.set_defaults(func=cmd_select)

    p_batch = sub.add_parser("batch-select")
    p_batch.add_argument("--parts-file")
    p_batch.add_argument("--parts-json")
    p_batch.add_argument("--json", action="store_true")
    p_batch.add_argument("--relevance-high", type=int, default=80, help="Score threshold for high relevance (default: 80)")
    p_batch.add_argument("--relevance-medium", type=int, default=30, help="Score threshold for medium relevance (default: 30)")
    p_batch.add_argument("--dry-run", action="store_true", help="Preview the plan without installing any skills")
    p_batch.set_defaults(func=cmd_batch_select)

    p_install = sub.add_parser("install")
    p_install.add_argument("package")
    p_install.add_argument("--json", action="store_true")
    p_install.set_defaults(func=cmd_install)

    p_remove = sub.add_parser("remove")
    p_remove.add_argument("skill_ref")
    p_remove.add_argument("--json", action="store_true")
    p_remove.set_defaults(func=cmd_remove)

    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser("check")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)

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
