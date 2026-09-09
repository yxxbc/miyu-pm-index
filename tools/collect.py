#!/usr/bin/env python3
"""Collect GitHub miyu packages and generate the standard index.

Usage:
  python tools/collect.py --schema schemas/miyu-package.schema.json --out .
  python tools/collect.py --schema schemas/miyu-package.schema.json --out /tmp/out --local ../examples/a ../examples/b
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml
from jsonschema import validate as json_schema_validate


REPO_NAME_PREFIX = "miyu-pm"
SEARCH_QUERY = "miyu-pm in:name"
MANIFEST_FILENAME = "miyu-package.yaml"
RISKY_SETUP_KEYWORDS = [
    "curl",
    "wget",
    "sudo",
    "chmod",
    "eval",
    "base64",
    "| sh",
    "bash -c",
    "rm ",
]
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(sessdata|cookie|token|secret|password|api[_-]?key|authorization)"
)


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_schema(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("miyu-package.yaml must contain a YAML mapping")
    return data


def path_is_safe(value: Any) -> bool:
    """Reject absolute paths and .. traversal in manifest file references."""
    if isinstance(value, str):
        if value.startswith("/") or "\\" in value:
            return False
        return ".." not in value.split("/")
    if isinstance(value, list):
        return all(path_is_safe(v) for v in value)
    return True


def static_security_checks(data: Dict[str, Any]) -> Dict[str, Any]:
    """Basic static preflight. Returns a security.static_checks object."""
    warnings: List[str] = []
    install = data.get("install") or {}
    setup = install.get("setup") or []
    for cmd in setup:
        for keyword in RISKY_SETUP_KEYWORDS:
            if keyword in cmd:
                warnings.append(f"setup command contains risky keyword '{keyword}': {cmd}")

    # path escape checks
    path_fields: List[tuple[str, Any]] = []
    if "path" in install:
        path_fields.append(("install.path", install.get("path")))
    skill = data.get("skill") or {}
    if "entry" in skill:
        path_fields.append(("skill.entry", skill.get("entry")))
    if "files" in skill:
        path_fields.append(("skill.files", skill.get("files")))
    script = data.get("script") or {}
    if "files" in script:
        path_fields.append(("script.files", script.get("files")))
    mcp = data.get("mcp") or {}
    if "args" in mcp:
        path_fields.append(("mcp.args", mcp.get("args")))
    plugin = data.get("plugin") or {}
    if "entry" in plugin:
        path_fields.append(("plugin.entry", plugin.get("entry")))

    for field, value in path_fields:
        if not path_is_safe(value):
            return {
                "status": "failed",
                "warnings": [f"unsafe path in {field}: {value}"],
                "checked_at": utc_now(),
            }

    # obvious literal secrets in env-like values
    env_holder = data.get("mcp") or {}
    env = env_holder.get("env") or {}
    for key, value in env.items():
        if isinstance(value, str) and SECRET_VALUE_PATTERN.search(key):
            if not value.startswith("{") or not value.endswith("}"):
                warnings.append(
                    f"env '{key}' looks like a literal secret; use {{env:...}} or {{user:...}}"
                )

    return {
        "status": "passed" if not warnings else "warned",
        "warnings": warnings,
        "checked_at": utc_now(),
    }


def normalize_manifest(
    data: Dict[str, Any],
    *,
    repo: str,
    full_name: str,
    default_branch: Optional[str],
    commit: Optional[str],
    archived: bool,
) -> Dict[str, Any]:
    checks = static_security_checks(data)
    if checks["status"] == "failed":
        raise ValueError("; ".join(checks["warnings"]))
    name = data.get("name")
    if not name:
        raise ValueError("manifest is missing name")
    entry: Dict[str, Any] = {
        "name": name,
        "display_name": data.get("display_name"),
        "description": data.get("description", ""),
        "type": data.get("type"),
        "version": data.get("version", ""),
        "license": data.get("license"),
        "homepage": data.get("homepage") or repo,
        "repo": repo,
        "manifest_path": MANIFEST_FILENAME,
        "default_branch": default_branch,
        "commit": commit,
        "archived": archived,
        "security": {
            "trust": "community",
            "reviewed_at": None,
            "static_checks": checks,
            "community_reports": {
                "total": 0,
                "positive": 0,
                "negative": 0,
                "latest": None,
            },
        },
    }
    for section in ("install", "mcp", "skill", "script", "plugin"):
        if section in data:
            entry[section] = data[section]
    return entry


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clean_stale_package_files(out: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    """Remove packages/*.json files that are no longer present in the index."""
    packages_dir = out / "packages"
    if not packages_dir.exists():
        return
    valid = {f"{name}.json" for name in entries}
    for path in sorted(packages_dir.glob("*.json")):
        if path.name not in valid:
            path.unlink()
            print(f"removed stale package file {path.name}")


def load_existing_packages(out: Path) -> List[Dict[str, Any]]:
    index_path = out / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return data.get("packages", []) if isinstance(data, dict) else []
    except Exception:
        return []


def build_change_summary(
    out: Path,
    entries: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    old = {p.get("name"): p for p in load_existing_packages(out) if p.get("name")}
    new = dict(entries)

    added = []
    for name in sorted(set(new) - set(old)):
        added.append(new[name])

    updated = []
    for name in sorted(set(old) & set(new)):
        if old[name].get("version") != new[name].get("version") or old[name].get("commit") != new[name].get("commit"):
            updated.append(
                {
                    "name": name,
                    "old": old[name],
                    "new": new[name],
                }
            )

    removed = []
    for name in sorted(set(old) - set(new)):
        removed.append(old[name])

    def short_names(items, key="name") -> str:
        names = [str(item[key]) for item in items]
        if len(names) <= 3:
            return ", ".join(names)
        return f"{', '.join(names[:3])} (+{len(names) - 3})"

    parts = []
    if added:
        parts.append(f"add {short_names(added)}")
    if updated:
        parts.append(f"update {short_names(updated)}")
    if removed:
        parts.append(f"remove {short_names(removed)}")
    if not parts:
        title = "chore: no package changes"
    else:
        title = "chore: " + ", ".join(parts)

    body_parts = ["## Changes", ""]
    for item in added:
        body_parts.append(
            f"- **add** `{item['name']}` v{item.get('version', '?')} "
            f"({item.get('type', '?')}) — {item.get('repo', '?')}"
        )
    for item in updated:
        old_v = item["old"].get("version", "?")
        new_v = item["new"].get("version", "?")
        body_parts.append(
            f"- **update** `{item['name']}` v{old_v} → v{new_v} "
            f"({item['new'].get('type', '?')}) — {item['new'].get('repo', '?')}"
        )
    for item in removed:
        body_parts.append(
            f"- **remove** `{item['name']}` v{item.get('version', '?')} "
            f"({item.get('type', '?')}) — {item.get('repo', '?')}"
        )
    if not added and not updated and not removed:
        body_parts.append("- no package changes")
    body_parts.extend(
        [
            "",
            "## Security",
            "",
            "每个新增/更新包都经过 Schema 校验与静态安全预检。",
            "",
            "_Auto-generated by collect-registry_",
        ]
    )
    return {
        "title": title,
        "body": "\n".join(body_parts),
        "added": [
            {
                "name": item["name"],
                "version": item.get("version"),
                "type": item.get("type"),
                "repo": item.get("repo"),
                "security": item.get("security"),
            }
            for item in added
        ],
        "updated": [
            {
                "name": item["name"],
                "old_version": item["old"].get("version"),
                "new_version": item["new"].get("version"),
                "type": item["new"].get("type"),
                "repo": item["new"].get("repo"),
            }
            for item in updated
        ],
        "removed": [
            {
                "name": item["name"],
                "version": item.get("version"),
                "type": item.get("type"),
                "repo": item.get("repo"),
            }
            for item in removed
        ],
    }


def github_json(url: str, token: Optional[str], *, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        reset = response.headers.get("X-RateLimit-Reset")
        wait = max(int(reset) - int(time.time()), 1) if reset else 60
        print(f"rate limited; sleeping {wait}s", file=sys.stderr)
        time.sleep(wait)
        return github_json(url, token, params=params)
    response.raise_for_status()
    return response.json()


def discover_repos(token: Optional[str]) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    page = 1
    while page <= 10:
        data = github_json(
            "https://api.github.com/search/repositories",
            token,
            params={
                "q": SEARCH_QUERY,
                "per_page": "100",
                "page": str(page),
            },
        )
        items = data.get("items", [])
        for item in items:
            full_name = item.get("full_name") or ""
            repo_name = full_name.split("/")[-1].lower()
            if full_name and repo_name.startswith(REPO_NAME_PREFIX):
                found[full_name] = item
        if len(items) < 100:
            break
        page += 1
    print(f"discovered {len(found)} candidate repo(s)", file=sys.stderr)
    return found


def collect_curated(
    schema: Dict[str, Any],
    out: Path,
    token: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    """Load packages listed in curated.json (manually maintained allowlist)."""
    curated_path = out / "curated.json"
    entries: Dict[str, Dict[str, Any]] = {}
    if not curated_path.exists():
        return entries
    try:
        curated_data = json.loads(curated_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warning: cannot read curated.json: {exc}", file=sys.stderr)
        return entries

    for item in curated_data.get("packages", []):
        full_name = item.get("repo")
        manifest_rel = item.get("manifest")
        if not full_name or not manifest_rel:
            continue
        try:
            manifest_path = out / manifest_rel
            if not manifest_path.exists():
                raise FileNotFoundError(f"curated manifest not found: {manifest_path}")
            data = load_manifest(manifest_path)
            json_schema_validate(data, schema)
            default_branch = "main"
            commit = None
            archived = False
            if token:
                try:
                    repo_info = github_json(
                        f"https://api.github.com/repos/{full_name}",
                        token,
                    )
                    default_branch = repo_info.get("default_branch") or "main"
                    archived = bool(repo_info.get("archived"))
                    commit_info = github_json(
                        f"https://api.github.com/repos/{full_name}/commits/{default_branch}",
                        token,
                    )
                    commit = commit_info.get("sha")
                except Exception as exc:
                    print(
                        f"warning: cannot resolve curated repo {full_name}: {exc}",
                        file=sys.stderr,
                    )
            entry = normalize_manifest(
                data,
                repo=f"https://github.com/{full_name}",
                full_name=full_name,
                default_branch=default_branch,
                commit=commit,
                archived=archived,
            )
            entries[entry["name"]] = entry
        except Exception as exc:
            print(f"curated {full_name} error: {exc}", file=sys.stderr)
    return entries


def collect_remote(
    schema: Dict[str, Any],
    out: Path,
    token: Optional[str],
    summary_file: Optional[Path] = None,
) -> None:
    if not token:
        raise SystemExit("GITHUB_TOKEN is required for remote collection")
    repos = discover_repos(token)
    entries: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, Dict[str, Any]] = {}

    for full_name, repo in repos.items():
        branch = repo.get("default_branch") or "main"
        manifest_url = (
            f"https://raw.githubusercontent.com/{full_name}/{branch}/{MANIFEST_FILENAME}"
        )
        try:
            response = requests.get(manifest_url, timeout=30)
            if response.status_code == 404:
                continue  # name-prefix hit but no manifest: not a miyu package
            response.raise_for_status()
            data = yaml.safe_load(response.text)
            if not isinstance(data, dict):
                raise ValueError("manifest is not a mapping")
            json_schema_validate(data, schema)
            try:
                commit_info = github_json(
                    f"https://api.github.com/repos/{full_name}/commits/{branch}",
                    token,
                )
                commit = commit_info.get("sha")
            except Exception as exc:
                commit = None
                errors.setdefault(full_name, {})["commit_warning"] = str(exc)
            entry = normalize_manifest(
                data,
                repo=f"https://github.com/{full_name}",
                full_name=full_name,
                default_branch=branch,
                commit=commit,
                archived=bool(repo.get("archived")),
            )
            name = entry["name"]
            if name in entries:
                errors[f"duplicate-{name}"] = {
                    "error": f"duplicate package name {name}",
                    "repos": [entries[name].get("repo"), entry.get("repo")],
                }
                continue
            entries[name] = entry
        except Exception as exc:
            errors[full_name] = {"error": str(exc)}

    curated = collect_curated(schema, out, token)
    for name, entry in curated.items():
        if name in entries:
            print(f"curated package overrides auto-discovered {name}", file=sys.stderr)
        entries[name] = entry

    for name, entry in entries.items():
        write_json(
            out / "packages" / f"{name}.json",
            {
                "schema_version": 1,
                "name": name,
                "source": {
                    "repo": entry["repo"],
                    "default_branch": entry.get("default_branch"),
                    "commit": entry.get("commit"),
                    "manifest_path": MANIFEST_FILENAME,
                },
                "security": entry.get("security"),
                "manifest": {
                    key: entry[key]
                    for key in (
                        "name",
                        "display_name",
                        "description",
                        "type",
                        "version",
                        "license",
                        "homepage",
                        "install",
                        "mcp",
                        "skill",
                        "script",
                        "plugin",
                    )
                    if key in entry
                },
            },
        )

    clean_stale_package_files(out, entries)
    if summary_file is not None:
        write_json(summary_file, build_change_summary(out, entries))
    for repo_name, error in errors.items():
        write_json(out / "_errors" / f"{repo_name}.json", error)
    write_index(out, entries)


def collect_local(
    schema: Dict[str, Any],
    out: Path,
    dirs: List[str],
    summary_file: Optional[Path] = None,
) -> None:
    entries: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, Dict[str, Any]] = {}
    for directory in dirs:
        base = Path(directory)
        manifest_path = base / MANIFEST_FILENAME
        full_name = base.name
        try:
            if not manifest_path.exists():
                raise FileNotFoundError(f"{manifest_path} not found")
            data = load_manifest(manifest_path)
            json_schema_validate(data, schema)
            homepage = data.get("homepage") or ""
            repo = homepage if homepage else f"local:{full_name}"
            entry = normalize_manifest(
                data,
                repo=repo,
                full_name=full_name,
                default_branch=None,
                commit=None,
                archived=False,
            )
            name = entry["name"]
            if name in entries:
                errors[f"duplicate-{name}"] = {"error": f"duplicate package name {name}"}
                continue
            entries[name] = entry
        except Exception as exc:
            errors[full_name] = {"error": str(exc)}

    for name, entry in entries.items():
        write_json(
            out / "packages" / f"{name}.json",
            {
                "schema_version": 1,
                "name": name,
                "source": {
                    "repo": entry["repo"],
                    "default_branch": None,
                    "commit": None,
                    "manifest_path": MANIFEST_FILENAME,
                },
                "security": entry.get("security"),
                "manifest": {
                    key: entry[key]
                    for key in (
                        "name",
                        "display_name",
                        "description",
                        "type",
                        "version",
                        "license",
                        "homepage",
                        "install",
                        "mcp",
                        "skill",
                        "script",
                        "plugin",
                    )
                    if key in entry
                },
            },
        )

    clean_stale_package_files(out, entries)
    if summary_file is not None:
        write_json(summary_file, build_change_summary(out, entries))
    for repo_name, error in errors.items():
        write_json(out / "_errors" / f"{repo_name}.json", error)
    write_index(out, entries)


def write_index(out: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    packages = sorted(entries.values(), key=lambda item: item["name"].lower())
    write_json(
        out / "index.json",
        {
            "schema_version": 1,
            "generated_at": utc_now(),
            "package_count": len(packages),
            "packages": packages,
        },
    )
    print(f"wrote index.json with {len(packages)} package(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="miyu-pm registry collector")
    parser.add_argument("--schema", required=True, help="path to miyu-package.schema.json")
    parser.add_argument("--out", required=True, help="output directory (index repo root)")
    parser.add_argument(
        "--local",
        nargs="*",
        default=None,
        help="use local manifest directories instead of GitHub search",
    )
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--summary-file", default=None, help="write PR summary JSON to this path")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    schema = load_schema(Path(args.schema))
    summary_file = Path(args.summary_file) if args.summary_file else None
    if args.local:
        collect_local(schema, out, args.local, summary_file)
    else:
        collect_remote(schema, out, args.github_token, summary_file)


if __name__ == "__main__":
    main()
