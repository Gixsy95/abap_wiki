"""User-notes preservation across sub-headings (DATA-7 regression).

What it does: proves a user's notes survive re-render even when they contain their own
'## ' headings, by bounding the protected region with an explicit end sentinel.
How it works: feeds bodies (sentinel form and legacy form) to render.extract_user_notes
and asserts the full notes (including inner '## ' lines) round-trip.
Connections: protects inviolable rule #10 (never overwrite User notes).
"""

import render


def test_notes_with_inner_h2_roundtrip_via_sentinel():
    body = (
        "## User notes\n\nfirst\n\n## My own heading\nsecond\n"
        f"{render.USER_NOTES_END}\n\n## Sources\n_x_\n"
    )
    notes = render.extract_user_notes(body)
    assert "first" in notes and "My own heading" in notes and "second" in notes


def test_legacy_page_without_sentinel_falls_back_to_next_h2():
    body = "## User notes\n\nonly line\n\n## Sources\n_x_\n"
    assert render.extract_user_notes(body).strip() == "only line"
