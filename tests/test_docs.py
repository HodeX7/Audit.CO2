"""Docs must match the code (Ingestion & Ledger).

If a test here fails, the code changed without its Markdown, or the Markdown promises something the code
doesn't do. Fix the doc in the same PR. Rules: docs/features/README.md.
"""

from __future__ import annotations

import ast
import importlib
import json
import re
from pathlib import Path

import pytest

from carbonroom import cli
from carbonroom.ledger import db

REPO = Path(__file__).resolve().parents[1]
FEATURES = REPO / "docs" / "features"
FEATURE_DOCS = sorted(FEATURES.glob("*.md"))
HANDOFF = REPO / "docs" / "HANDOFF.md"
OWN_DOCS = FEATURE_DOCS + [HANDOFF, REPO / "docs" / "EXPLAIN_ingestion.md", REPO / "data" / "seed" / "README.md"]
OWN_COMMANDS = {"init", "seed", "ingest", "extract", "ledger", "llm", "graphdb"}  # teammates register their own
ENV_PREFIXES = ("CR_", "LLM_", "NVIDIA_", "ANTHROPIC_", "OPENAI_", "OPENROUTER_", "OLLAMA_", "NEO4J_")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code_segments(text: str) -> list[str]:
    """Inline `code` spans and the lines of fenced ``` blocks."""
    segments: list[str] = []
    fenced = re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.S)
    for block in fenced:
        segments.extend(block.splitlines())
    without_fences = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.S)
    segments.extend(re.findall(r"`([^`\n]+)`", without_fences))
    return segments


def inline_spans(text: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.S))


# --- carbonroom.ledger.db <-> HANDOFF ---------------------------------------------------------


def _handoff_db_section() -> str:
    text = read(HANDOFF)
    start = text.index("### `carbonroom.ledger.db`: function list")
    return text[start : text.index("Status rules", start)]


def test_every_public_db_function_is_in_the_handoff_table_and_vice_versa():
    tree = ast.parse(read(REPO / "carbonroom" / "ledger" / "db.py"))
    public = {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
    named = set(re.findall(r"`([a-z_][a-z0-9_]*)(?:\(|`)", _handoff_db_section()))
    assert public - named == set(), "add these to the docs/HANDOFF.md function table"
    assert {n for n in named if not hasattr(db, n)} == set(), "HANDOFF names functions db.py doesn't have"


def test_status_transitions_in_handoff_match_the_code():
    written = {
        src: {t.strip() for t in targets.split("|")}
        for src, targets in re.findall(r"`([A-Z]+) → ([A-Z |]+)`", read(HANDOFF))
    }
    in_code = {src: set(targets) for src, targets in db.ALLOWED_TRANSITIONS.items() if targets}
    assert written == in_code


# --- CLI commands and flags ---------------------------------------------------------------------


def _subparsers(parser):
    for action in parser._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            return action.choices
    return {}


def _commands_in(text: str):
    for segment in code_segments(text):
        for match in re.finditer(r"(?<![\w/.-])carbonroom\s+(.+)", segment):
            if segment[: match.start()].rstrip().endswith(("from", "import")):
                continue  # Python code, not a CLI command
            tokens = []
            for token in match.group(1).split():
                if token in ("#", "&&", "|", ";", "\\") or token.startswith("#"):
                    break
                tokens.append(token.strip(":,.)\"'[]"))
            if tokens and re.fullmatch(r"[a-z][a-z-]*|--?[a-z][\w-]*", tokens[0]):
                yield tokens


@pytest.mark.parametrize("doc", OWN_DOCS, ids=lambda p: p.name)
def test_every_documented_command_and_flag_exists(doc):
    top = _subparsers(cli.build_parser())
    problems = []
    for tokens in _commands_in(read(doc)):
        if tokens[0].startswith("-"):
            continue  # global flags (--db, --version)
        if tokens[0] not in top:
            problems.append(f"unknown command: carbonroom {tokens[0]}")
            continue
        leaf, rest = top[tokens[0]], tokens[1:]
        nested = _subparsers(leaf)
        if nested:
            if not rest or rest[0].startswith(("<", "-")):
                continue
            if rest[0] not in nested:
                problems.append(f"unknown command: carbonroom {tokens[0]} {rest[0]}")
                continue
            leaf, rest = nested[rest[0]], rest[1:]
        options = set(leaf._option_string_actions)
        for token in rest:
            flag = token.split("=", 1)[0]
            if re.fullmatch(r"--?[a-z][\w-]*", flag) and flag not in options:
                problems.append(f"unknown flag {flag} for: carbonroom {' '.join(tokens[:2])}")
    assert problems == []


def test_every_ingestion_and_ledger_command_is_documented_in_feature_docs():
    documented = {" ".join(t[:2]) for doc in FEATURE_DOCS for t in _commands_in(read(doc))}
    documented |= {t[0] for doc in FEATURE_DOCS for t in _commands_in(read(doc))}
    top = _subparsers(cli.build_parser())
    expected = set()
    for name in OWN_COMMANDS:
        nested = _subparsers(top[name])
        expected |= {f"{name} {sub}" for sub in nested} if nested else {name}
    assert expected - documented == set(), "document these commands in docs/features/"


def test_every_flag_of_our_commands_is_documented_in_feature_docs():
    text = "\n".join(read(doc) for doc in FEATURE_DOCS)
    top = _subparsers(cli.build_parser())
    leaves = {"carbonroom": cli.build_parser()}
    for name in OWN_COMMANDS:
        nested = _subparsers(top[name])
        leaves.update({f"{name} {sub}": p for sub, p in nested.items()} if nested else {name: top[name]})
    undocumented = sorted(
        f"{cmd} {flag}"
        for cmd, parser in leaves.items()
        for flag in parser._option_string_actions
        if flag.startswith("--") and flag != "--help" and f"`{flag}" not in text and f" {flag}" not in text
    )
    assert undocumented == [], "document these flags in docs/features/"


# --- environment variables ----------------------------------------------------------------------


def test_env_vars_read_by_the_code_are_in_env_example_and_vice_versa():
    from carbonroom import llm

    code = "\n".join(read(p) for p in (REPO / "carbonroom").rglob("*.py"))
    literal = {v for v in re.findall(r'"([A-Z][A-Z0-9_]+)"', code) if v.startswith(ENV_PREFIXES)}
    generated = {f"LLM_{f}" for f in llm.TASK_OVERRIDE_FIELDS}  # read via llm.setting()
    per_task = {f"LLM_{f}_{t.upper()}" for f in llm.TASK_OVERRIDE_FIELDS for t in llm.KNOWN_TASKS}
    example = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", read(REPO / ".env.example"), flags=re.M))
    assert (literal | generated) - example == set(), "add these to .env.example"
    listed = {v for v in example if v.startswith(ENV_PREFIXES)}
    assert listed - (literal | generated | per_task) == set(), ".env.example lists vars the code never reads"


# --- paths, links and dotted names ----------------------------------------------------------------


@pytest.mark.parametrize("doc", FEATURE_DOCS, ids=lambda p: p.name)
def test_paths_links_and_names_in_feature_docs_exist(doc):
    text = read(doc)
    missing = []
    for span in inline_spans(text):
        token = span.split()[0] if span.split() else ""
        if re.fullmatch(r"(?:carbonroom|data|contracts|tests|docs)/[\w./-]*", token):
            if token.startswith("data/store") or not (REPO / token).exists():
                if not token.startswith("data/store"):
                    missing.append(token)
        if re.fullmatch(r"carbonroom(?:\.\w+)+", token):
            parts = token.split(".")
            for cut in range(len(parts), 0, -1):
                try:
                    obj = importlib.import_module(".".join(parts[:cut]))
                except ModuleNotFoundError:
                    continue
                try:
                    for attr in parts[cut:]:
                        obj = getattr(obj, attr)
                except AttributeError:
                    missing.append(token)
                break
            else:
                missing.append(token)
    for link in re.findall(r"\]\(([^)#\s]+)\)", text):
        if not link.startswith("http") and not (doc.parent / link).exists():
            missing.append(link)
    assert missing == []


@pytest.mark.parametrize("doc", [d for d in FEATURE_DOCS if d.name != "README.md"], ids=lambda p: p.name)
def test_feature_docs_have_the_required_sections(doc):
    text = read(doc)
    for heading in ("## Why", "## Design", "## Decisions", "## Code map", "## Tests"):
        assert heading in text, f"{doc.name} is missing '{heading}'"


# --- schema and kinds ---------------------------------------------------------------------------


def test_ledger_doc_lists_every_table_view_and_kind():
    spans = set(inline_spans(read(FEATURES / "ledger.md")))
    schema = read(REPO / "contracts" / "schema.sql")
    tables = set(re.findall(r"CREATE (?:TABLE|VIEW) IF NOT EXISTS (\w+)", schema))
    assert tables - spans == set()
    assert set(db.GAP_KINDS) - spans == set()
    assert set(db.DOC_KINDS) - spans == set()


# --- cache labels and seed numbers ----------------------------------------------------------------


def test_docs_name_the_producer_of_the_committed_extraction_cache():
    labels = {json.loads(read(p))["proposer"] for p in (REPO / "data" / "seed" / "extractions").glob("*.json")}
    for doc in (REPO / "THIRD_PARTY.md", FEATURES / "seed-data.md"):
        assert {label for label in labels if label not in read(doc)} == set(), doc.name


def test_seed_readme_lists_every_seed_document():
    readme = read(REPO / "data" / "seed" / "README.md")
    manifest = json.loads(read(REPO / "data" / "seed" / "manifest.json"))
    assert [e["file"] for e in manifest if e["file"] not in readme] == []


def test_knowledge_graph_examples_match_the_code(env, capsys):
    from carbonroom.cli import main

    main(["seed"])
    main(["ingest", "data/seed/later/2026-10_austin_electricity_ELB-AUS-2610-C.pdf", "--from", "omar",
          "--room", "cr-site-austin"])
    text = read(FEATURES / "knowledge-graph.md")
    for name, argv in (("trace", ["ledger", "trace", "ACT-0739d5932d"]), ("impact", ["ledger", "impact", "ELB-AUS-2610"]),
                       ("graph", ["ledger", "graph", "--period", "2026-10", "--site", "austin"])):
        capsys.readouterr()
        main(argv)
        actual = capsys.readouterr().out
        block = re.search(rf"<!-- example:{name}:start -->\n```\w+\n(.*?)```\n<!-- example:{name}:end -->", text, re.S)
        assert block, f"example:{name} markers missing"
        documented = block.group(1)
        if name != "graph":
            documented = documented.split("\n", 1)[1]  # drop the "$ carbonroom ..." line
        assert documented.rstrip("\n") == actual.rstrip("\n"), f"regenerate the {name} example in knowledge-graph.md"


def test_seed_counts_written_in_docs_match_a_real_seed(env):
    from carbonroom.ingest.seed import run_seed

    summary = run_seed(env / "count.db")
    actual = (summary["documents"], summary["activities"])
    for doc in (FEATURES / "seed-data.md", REPO / "data" / "seed" / "README.md"):
        claims = [(int(a), int(b)) for a, b in re.findall(r"(\d+) documents, (\d+) activities", read(doc))]
        assert claims and all(c == actual for c in claims), (doc.name, claims, actual)
