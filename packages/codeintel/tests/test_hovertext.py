from __future__ import annotations

from codeintel.hovertext import hover_to_signature_and_doc


def test_none_hover() -> None:
    assert hover_to_signature_and_doc(None) == (None, None)


def test_fenced_signature_and_doc() -> None:
    hover = {
        "contents": {"kind": "markdown", "value": "```cpp\nint foo(int x)\n```\nDoes a thing."}
    }
    signature, doc = hover_to_signature_and_doc(hover)
    assert signature == "int foo(int x)"
    assert doc == "Does a thing."


def test_fenced_signature_only() -> None:
    hover = {"contents": {"value": "```cpp\nint foo()\n```"}}
    signature, doc = hover_to_signature_and_doc(hover)
    assert signature == "int foo()"
    assert doc is None


def test_plain_string_contents() -> None:
    signature, doc = hover_to_signature_and_doc({"contents": "just some text"})
    assert signature is None
    assert doc == "just some text"


def test_list_of_marked_strings() -> None:
    hover = {"contents": ["```cpp\nint foo()\n```", "extra note"]}
    signature, doc = hover_to_signature_and_doc(hover)
    assert signature == "int foo()"
    assert doc == "extra note"
