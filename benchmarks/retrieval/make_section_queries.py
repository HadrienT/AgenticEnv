"""Builds `queries-sections.yaml`: passage-level reference queries for `kbase eval`.

For a seeded sample of content sections (curated like ingestion does), the local LLM
writes one paraphrased question the section answers. The expected answer is that
document *and* that section, which scores retrieval of the passage, not only of the
book. Questions that copy five consecutive words of the passage are rejected: they
would only measure lexical overlap.

    AGX_KBASE_CONFIG=kbase-v2.yaml uv run python benchmarks/retrieval/make_section_queries.py

Generated once and versioned; regenerate only when the corpus changes.
"""

from __future__ import annotations

import json
import random
import re
import sys
import urllib.request
from pathlib import Path

import yaml
from corelib.config import get_settings, repo_root
from kbase.config import load_kbase_config
from kbase.ingestion import curation, sources
from kbase.ingestion.chunking import approx_tokens
from kbase.ingestion.parsers.markdown import MarkdownParser

LLM_URL = "http://127.0.0.1:8000/v1/chat/completions"
SEED = 20261109
MIN_SECTION_TOKENS = 250
PASSAGE_CHARS = 3000
# Off-topic for a pricing library: fewer samples, so they do not dominate the score.
LIGHT = {
    "boyd-vandenberghe-convex-optimization",
    "wooldridge-introductory-econometrics",
    "tsay-analysis-financial-time-series",
    "ohara-market-microstructure-theory",
    "zhou-quant-finance-interviews",
}
PER_BOOK, PER_LIGHT_BOOK, PER_PAPER = 8, 3, 2
PROMPT = (
    "Here is a passage from a quantitative finance book or paper.\n\n<passage>\n{passage}\n"
    "</passage>\n\nWrite ONE question, 8 to 25 words, that a quant developer could type into a "
    "search engine and that this passage answers specifically. Paraphrase: never copy four or "
    "more consecutive words from the passage, and never mention the passage, the author, the "
    "book or the paper. Reply with the question only."
)
_WORD_RE = re.compile(r"[a-z0-9]+")
_BANNED = ("passage", "this section", "the author", "the paper", "the book", "this text")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _copies(question: str, passage: str, n: int = 5) -> bool:
    words = _words(question)
    haystack = " " + " ".join(_words(passage)) + " "
    return any(
        f" {' '.join(words[i : i + n])} " in haystack for i in range(len(words) - n + 1)
    )


def _ask(passage: str) -> str:
    body = {
        "model": "local",
        "messages": [{"role": "user", "content": PROMPT.format(passage=passage)}],
        "temperature": 0.2,
        "max_tokens": 80,
    }
    request = urllib.request.Request(
        LLM_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        reply = json.load(response)["choices"][0]["message"]["content"]
    return " ".join(reply.strip().strip('"').split())


def main() -> int:
    config = load_kbase_config()
    patterns = curation.compile_patterns(config.curation.drop_sections)
    documents_dir = get_settings().paths.documents_dir
    rng = random.Random(SEED)
    queries: list[dict[str, object]] = []
    for item in sources.resolve(repo_root() / "documents/manifest.yaml", documents_dir):
        doc = curation.drop_sections(
            MarkdownParser().parse(Path(item.resolved_path), item.meta), patterns
        )
        text_of: dict[str, list[str]] = {}
        for block in doc.blocks:
            if block.section_id and block.kind == "text":
                text_of.setdefault(block.section_id, []).append(block.text)
        candidates = [
            s
            for s in doc.sections
            if s.level >= 2
            and sum(approx_tokens(t) for t in text_of.get(s.section_id, [])) >= MIN_SECTION_TOKENS
        ]
        key = item.meta.doc_key
        want = (
            PER_PAPER
            if item.meta.doc_type == "research_paper"
            else PER_LIGHT_BOOK
            if key in LIGHT
            else PER_BOOK
        )
        rng.shuffle(candidates)
        kept = 0
        for section in candidates:
            if kept == want:
                break
            passage = "\n\n".join(text_of[section.section_id])[:PASSAGE_CHARS]
            question = _ask(f"{section.title}\n\n{passage}")
            if (
                not 8 <= len(question.split()) <= 30
                or any(b in question.lower() for b in _BANNED)
                or _copies(question, passage)
            ):
                continue
            queries.append(
                {
                    "category": "section",
                    "text": question,
                    "expected": [key],
                    "expected_sections": [section.title],
                }
            )
            kept += 1
        print(f"{key}: {kept}/{want}", file=sys.stderr)
    out = repo_root() / "benchmarks/retrieval/queries-sections.yaml"
    header = (
        "# Passage-level reference queries, generated by make_section_queries.py (seeded).\n"
        "# A hit is a chunk of the expected document carrying the expected section title.\n"
        "# Only one document is expected, though others may answer too: compare runs with\n"
        "# each other, not with the absolute numbers of queries.yaml.\n"
    )
    out.write_text(
        header + yaml.safe_dump({"queries": queries}, sort_keys=False, allow_unicode=True, width=200),
        encoding="utf-8",
    )
    print(f"{len(queries)} queries -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
