#!/usr/bin/env python3
"""The gate CI runs before anything else: standard library only.

  1. duck.py must compile and its selftest must PASS. The selftest drives the hooks on
     recorded fixtures; a duck whose hash differs from its sealed MANIFEST.json fails
     closed, so an edit without `python3 duck.py seal` fails here.
  2. MANIFEST.json must name this duck.py by hash and list every fixture by hash; the
     version must agree across duck.py, both plugin manifests and the seal; hooks may
     reference only files that exist under this root; the Codex manifest's paths must exist.
  3. every skills/*/SKILL.md must carry frontmatter whose description is a quoted string
     (an unquoted colon silently empties the metadata at runtime).
  4. English is the only language of code, comments, copy and the Agent Code.
  5. every workflow must pin its actions to a commit SHA and declare its permissions.

Exit 0 only when everything holds. Findings are printed as a table.
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DUCK = ROOT / "duck.py"


def _sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _version_in_source():
    m = re.search(r'^VERSION = "([^"]+)"$', DUCK.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def check_selftest(rows):
    try:
        compile(DUCK.read_text(encoding="utf-8"), str(DUCK), "exec")
        rows.append(("duck.py compiles", True, ""))
    except SyntaxError as exc:
        rows.append(("duck.py compiles", False, "line %s" % exc.lineno))
        return
    r = subprocess.run([sys.executable, str(DUCK), "selftest"], capture_output=True, text=True)
    ok = r.returncode == 0 and r.stdout.strip().endswith("PASS")
    rows.append(("duck selftest", ok, "" if ok else (r.stdout.strip().splitlines() or [r.stderr[-200:]])[-1]))


def check_manifests(rows):
    version = _version_in_source()
    rows.append(("duck.py declares a version", bool(version), version or "no VERSION line"))
    parsed = {}
    for rel in ("MANIFEST.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
                "hooks/hooks.json", "codex/hooks.json", "fixtures/gates.json", "fixtures/dissent.json"):
        try:
            parsed[rel] = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            rows.append((rel, True, ""))
        except (OSError, ValueError) as exc:
            rows.append((rel, False, str(exc)[:80]))
    manifest = parsed.get("MANIFEST.json", {})
    sealed = manifest.get("duck_sha256") == _sha(DUCK)
    rows.append(("MANIFEST.json seals this duck.py", sealed, "" if sealed else "run: python3 duck.py seal"))
    stale = [name for name, sha in manifest.get("fixtures_sha256", {}).items()
             if not (ROOT / "fixtures" / name).exists() or _sha(ROOT / "fixtures" / name) != sha]
    unlisted = [p.name for p in (ROOT / "fixtures").glob("*.json") if p.name not in manifest.get("fixtures_sha256", {})]
    rows.append(("fixtures match the seal", not stale and not unlisted, ", ".join(stale + unlisted)))
    versions = {"duck.py": version, "MANIFEST.json": manifest.get("version"),
                ".claude-plugin/plugin.json": parsed.get(".claude-plugin/plugin.json", {}).get("version"),
                ".codex-plugin/plugin.json": parsed.get(".codex-plugin/plugin.json", {}).get("version")}
    agree = len(set(versions.values())) == 1 and None not in versions.values()
    rows.append(("version agrees across duck.py, manifests and seal", agree,
                 version if agree else ", ".join("%s %s" % kv for kv in versions.items())))
    names = {rel: parsed.get(rel, {}).get("name") for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json")}
    same_name = len(set(names.values())) == 1 and None not in names.values()
    rows.append(("plugin name agrees across both manifests", same_name, next(iter(names.values())) or "missing"))
    missing = []
    for rel in ("hooks/hooks.json", "codex/hooks.json"):
        for event, groups in parsed.get(rel, {}).get("hooks", {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    for m in re.finditer(r'\$\{?(?:CLAUDE_)?PLUGIN_ROOT\}?/([\w./-]+)', h.get("command", "")):
                        if not (ROOT / m.group(1)).exists():
                            missing.append("%s %s: %s" % (rel, event, m.group(1)))
    rows.append(("hooks reference existing files under this root", not missing, ", ".join(missing)))
    codex = parsed.get(".codex-plugin/plugin.json", {})
    refs = [codex.get("hooks", ""), codex.get("skills", ""), (codex.get("interface") or {}).get("logo", "")]
    bad = [r for r in refs if r and not (ROOT / r).exists()]
    rows.append(("codex manifest paths exist", not bad, ", ".join(bad)))


def check_skills(rows):
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = skill.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n", text, re.S)
        ok = bool(m) and bool(re.search(r'^description: "[^"\n]+"$', m.group(1), re.M))
        rows.append(("skill %s frontmatter" % skill.parent.name, ok, "" if ok else "description must be a quoted string"))


# Cyrillic, Hebrew and Arabic, Indic, Thai, Japanese kana, CJK ideographs, Hangul and
# full-width forms, built from code points so this file stays ASCII and passes its own check.
NON_LATIN_RANGES = ((0x0400, 0x04FF), (0x0590, 0x06FF), (0x0900, 0x0DFF), (0x0E00, 0x0E7F),
                    (0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF),
                    (0xFF00, 0xFFEF))
NON_LATIN = re.compile("[" + "".join("%s-%s" % (chr(a), chr(b)) for a, b in NON_LATIN_RANGES) + "]")
TEXT_SUFFIXES = {".py", ".md", ".html", ".json", ".yml", ".yaml", ".css", ".txt", ".sh", ".svg"}


def check_english_only(rows):
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        rel = p.relative_to(ROOT)
        if rel.parts[0] in (".git", "dist", "node_modules", "__pycache__"):
            continue
        try:
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if NON_LATIN.search(line):
                    hits.append("%s:%d" % (rel, n))
        except (OSError, UnicodeDecodeError):
            continue
    rows.append(("english only (no non-Latin scripts)", not hits, ", ".join(hits[:6]) + (" ..." if len(hits) > 6 else "")))


def check_workflows(rows):
    unpinned, unscoped = [], []
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for m in re.finditer(r"^\s*-?\s*uses:\s*(\S+)", text, re.M):
            if not re.search(r"@[0-9a-f]{40}$", m.group(1)):
                unpinned.append("%s: %s" % (wf.name, m.group(1)))
        if not re.search(r"^permissions:", text, re.M):
            unscoped.append(wf.name)
    rows.append(("workflow actions pinned to a commit SHA", not unpinned, ", ".join(unpinned)))
    rows.append(("workflows declare permissions", not unscoped, ", ".join(unscoped)))


def main():
    rows = []
    check_selftest(rows)
    check_manifests(rows)
    check_skills(rows)
    check_english_only(rows)
    check_workflows(rows)
    width = max(len(r[0]) for r in rows)
    for name, ok, note in rows:
        print("  %-5s %-*s %s" % ("ok" if ok else "FAIL", width, name, note))
    failed = [r for r in rows if not r[1]]
    print("\n%s" % ("CHECK PASS" if not failed else "CHECK FAIL (%d)" % len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
