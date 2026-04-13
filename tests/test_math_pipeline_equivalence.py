"""Targeted trace test for math pipeline equivalence.

Run with:
    pytest -s tests/test_math_pipeline_equivalence.py
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import quote, quote_plus, unquote_plus

import mdtopdf.core.parser as parser_module
from mdtopdf.core.parser import MarkdownParser


def _normalize_ws(s: str) -> str:
    return " ".join(s.split())


def test_math_pipeline_equivalence_trace(monkeypatch):
    # Keep the sample intentionally small so each stage is easy to inspect.
    md = (
        "定义：\\[\n"
        "X(e^{j\\omega}) = \\sum_{n=-\\infty}^{\\infty} x[n] e^{-j\\omega n}\n"
        "\\]\n"
        "其中 \\( X(e^{j\\omega}) \\) 是复函数。\n"
    )

    expected_block = r"X(e^{j\omega}) = \sum_{n=-\infty}^{\infty} x[n] e^{-j\omega n}"
    expected_inline = r"X(e^{j\omega})"

    captured: list[dict[str, str]] = []

    def fake_get(url: str, **kwargs):
        query = url.split("?", 1)[1] if "?" in url else ""
        decoded = unquote_plus(query)
        captured.append(
            {
                "url": url,
                "query": query,
                "decoded": decoded,
                "timeout": str(kwargs.get("timeout")),
            }
        )
        # Minimal fake PNG payload so renderer can continue to base64 stage.
        return SimpleNamespace(status_code=200, content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)

    monkeypatch.setattr(parser_module.requests, "get", fake_get)

    parser = MarkdownParser(
        math_mode="online",
        online_providers=["codecogs_png"],
        enable_bare_latex=False,
    )
    result = parser.parse_string(md)

    print("\n=== Stage 1: expected extracted formulas ===")
    print("block:", expected_block)
    print("inline:", expected_inline)

    print("\n=== Stage 2: URL/query generated for API ===")
    for i, item in enumerate(captured, start=1):
        print(f"#{i} url      : {item['url']}")
        print(f"#{i} query    : {item['query']}")
        print(f"#{i} decoded  : {item['decoded']}")
        print(f"#{i} timeout  : {item['timeout']}")

    print("\n=== Stage 3: encoding comparison (for + issue diagnosis) ===")
    print("quote_plus(block):", quote_plus(expected_block))
    print("quote(block)     :", quote(expected_block, safe=""))
    print("quote_plus(inline):", quote_plus(expected_inline))
    print("quote(inline)     :", quote(expected_inline, safe=""))
    codecogs_queries = [item["query"] for item in captured if "latex.codecogs.com" in item["url"]]
    print("codecogs queries contain '+' from urlencode:", any("+" in q for q in codecogs_queries))

    print("\n=== Stage 4: rendered HTML indicators ===")
    print("math-img-inline count:", result.html_body.count("math-img-inline"))
    print("math-img-block count :", result.html_body.count("math-img-block"))
    print("has base64 image     :", "data:image/png;base64," in result.html_body)

    # Equivalence checks (ignore whitespace differences from markdown source formatting)
    decoded_formulas = {_normalize_ws(item["decoded"]) for item in captured}
    assert _normalize_ws(expected_block) in decoded_formulas
    assert _normalize_ws(expected_inline) in decoded_formulas
    assert "data:image/png;base64," in result.html_body
    # For this sample, '+' should not come from URL encoding in CodeCogs query.
    assert not any("+" in q for q in codecogs_queries)

