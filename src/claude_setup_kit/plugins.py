"""Plugin and marketplace manifests.

Claude Code has its own validator and it is the authority. This check is the
cheap one that runs everywhere, including CI where `claude` is not installed: the
manifest parses, and it carries the fields without which the plugin cannot be
addressed at all.
"""

from __future__ import annotations

import json
from pathlib import Path

from .common import Check, Finding, rel


def check_manifests(root: Path, cfg) -> list[Check]:
    marketplace = root / ".claude-plugin" / "marketplace.json"
    plugin_manifests = sorted(root.glob("plugins/*/.claude-plugin/plugin.json"))
    if (root / ".claude-plugin" / "plugin.json").is_file():
        plugin_manifests.append(root / ".claude-plugin" / "plugin.json")

    checks = [
        Check("INV-26", "the marketplace manifest parses and lists real plugin directories"),
        Check("INV-27", "every plugin manifest parses and carries name and description"),
    ]

    if not marketplace.is_file():
        checks[0].applicable = False
    else:
        checks[0].examined = 1
        try:
            data = json.loads(marketplace.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            checks[0].findings.append(
                Finding("INV-26", rel(marketplace, root), f"invalid JSON: {exc}")
            )
            data = None
        if isinstance(data, dict):
            if not data.get("name"):
                checks[0].findings.append(
                    Finding("INV-26", rel(marketplace, root), "no marketplace name")
                )
            entries = data.get("plugins")
            if not isinstance(entries, list) or not entries:
                checks[0].findings.append(
                    Finding("INV-26", rel(marketplace, root), "no plugins listed")
                )
            else:
                for entry in entries:
                    source = entry.get("source") if isinstance(entry, dict) else None
                    if isinstance(source, str) and source.startswith("."):
                        if not (root / source).is_dir():
                            checks[0].findings.append(
                                Finding(
                                    "INV-26",
                                    rel(marketplace, root),
                                    f"entry {entry.get('name')!r} points at a missing directory: {source}",
                                )
                            )

    if not plugin_manifests:
        checks[1].applicable = False
        return checks

    checks[1].examined = len(plugin_manifests)
    for manifest in plugin_manifests:
        relative = rel(manifest, root)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            checks[1].findings.append(Finding("INV-27", relative, f"invalid JSON: {exc}"))
            continue
        for field in ("name", "description"):
            if not data.get(field):
                checks[1].findings.append(Finding("INV-27", relative, f"no {field}"))
        expected = manifest.parent.parent.name
        if data.get("name") and data["name"] != expected and expected != root.name:
            checks[1].findings.append(
                Finding(
                    "INV-27",
                    relative,
                    f"name {data['name']!r} but directory {expected!r}",
                )
            )
    return checks
