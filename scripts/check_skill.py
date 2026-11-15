"""Keep the bundled skill and plugin files in step with the server.

    python scripts/check_skill.py   # exit 1 and list problems if anything is out of date

Checks: SKILL.md frontmatter (name, description, length limits), every relative link resolves,
every tool name the skill mentions really exists on the server, and the plugin manifests agree
with the package version.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
# snake_case words in backticks that are parameters or values, not tool names
NOT_TOOLS = {"confirm_scratch", "plan_input_id", "wire_layers", "user_confirmed", "unit_to_m",
             "dry_run", "unconnected_pin", "duplicate_wire_number", "missing_catalog",
             "load_schedule", "unit_scale_vs_mm", "acad_electrical_mcp"}
TOOLISH = re.compile(r"`([a-z]+(?:_[a-z0-9]+)+)`")


def problems() -> list[str]:
    sys.path.insert(0, str(ROOT / "src"))
    from acad_electrical_mcp import __version__, server

    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    out: list[str] = []
    for skill in sorted(SKILLS.glob("*/SKILL.md")):
        text = skill.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            out.append(f"{skill}: missing YAML frontmatter")
            continue
        fm = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
        name, desc = fm.get("name", "").strip(), fm.get("description", "").strip()
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name) or name != skill.parent.name:
            out.append(f"{skill}: name must be lowercase-hyphenated and match its folder")
        if not desc or len(desc) > 1024:
            out.append(f"{skill}: description missing or over 1024 characters")
        for md in [skill, *sorted(skill.parent.rglob("references/*.md"))]:
            body = md.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)#\s]+)", body):
                if not target.startswith("http") and not (md.parent / target).exists():
                    out.append(f"{md.relative_to(ROOT)}: broken link {target}")
            for word in TOOLISH.findall(body):
                if word not in tools and word not in NOT_TOOLS:
                    out.append(f"{md.relative_to(ROOT)}: `{word}` is not a server tool")
    for manifest in (ROOT / ".claude-plugin" / "plugin.json",):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("version") != __version__:
            out.append(f"{manifest.name}: version {data.get('version')} != package {__version__}")
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    for p in market["plugins"]:
        if p.get("version") != __version__:
            out.append(f"marketplace.json: {p['name']} version {p.get('version')} != {__version__}")
    return out


def main() -> int:
    found = problems()
    for p in found:
        print(p)
    if not found:
        print("skills and plugin files are in step with the server")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
