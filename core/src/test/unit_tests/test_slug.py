"""Test 1 - slug sanitisation (slugs.py).

What it does: verifies slug sanitisation (Test 1) that encodes the lesson of the /NS/ bug - stripping of namespaced slashes, no path separators ever, upper-case normalisation, padding/space collapsing, removal of trailing dots and Windows-reserved characters, safe devclass dir, empty-name fallback, ~NS suffix on collision, and length threshold.
How it works: pytest with no fixtures; calls slugs.make_slug/safe_devclass_dir/sanitize_name/slug_too_long directly with boundary inputs and asserts on exact output.
Connections: exercises slugs; no conftest.py fixtures.
"""

import slugs


def test_namespaced_name_strips_slashes():
    assert slugs.make_slug("data-element", "/ECRS/POIID") == "data-element-ECRS_POIID"
    assert slugs.make_slug("include", "/ABC/COMON") == "include-ABC_COMON"


def test_no_path_separators_ever():
    for name in ("/A/B", "A/B/C", "//X//", "/NS/NAME/EXTRA"):
        slug = slugs.make_slug("program", name)
        assert "/" not in slug and "\\" not in slug


def test_plain_name_unchanged():
    assert slugs.make_slug("program", "ZPROGRAM") == "program-ZPROGRAM"


def test_lowercase_is_normalized_upper():
    # abap_wiki lookups are case-insensitive: there is a single slug, uppercase
    assert slugs.make_slug("class", "cl_gui_frontend_services") == slugs.make_slug(
        "class", "CL_GUI_FRONTEND_SERVICES"
    )


def test_padding_and_spaces_collapse():
    # composite TADIR keys with padding (e.g. abap-query 'ZEX   ZEXAMPLE_QUERY')
    assert (
        slugs.make_slug("abap-query", "ZEX         ZEXAMPLE_QUERY")
        == "abap-query-ZEX_ZEXAMPLE_QUERY"
    )
    assert slugs.make_slug("tadir-iwmo", "ZX  0001") == "tadir-iwmo-ZX_0001"


def test_trailing_dots_removed():
    # trailing dots are not allowed: no filenames ending with a dot on Windows
    slug = slugs.make_slug("table", "ZTAB.")
    assert not slug.endswith(".")
    assert slug == "table-ZTAB"


def test_dollar_tmp_preserved():
    assert slugs.safe_devclass_dir("$TMP") == "$TMP"


def test_devclass_namespaced():
    assert slugs.safe_devclass_dir("/ECRS/BL_MD") == "ECRS_BL_MD"


def test_empty_name_fallback():
    assert slugs.sanitize_name("") == "UNNAMED"
    assert slugs.sanitize_name("...") == "UNNAMED"


def test_ns_suffix_on_collision():
    base = slugs.make_slug("data-element", "/ABC/COMON")
    suffixed = slugs.make_slug("data-element", "/ABC/COMON", ns_suffix=True)
    assert suffixed == base + "~NS"
    assert suffixed != slugs.make_slug("data-element", "ABC_COMON")


def test_windows_reserved_chars_removed():
    for ch in '<>:"|?*':
        slug = slugs.make_slug("program", f"Z{ch}X")
        assert ch not in slug


def test_length_warning():
    assert slugs.slug_too_long("x" * 121)
    assert not slugs.slug_too_long("x" * 120)


def test_make_slug_disambiguator_sequence():
    assert slugs.make_slug("class", "/NS/X") == "class-NS_X"
    assert slugs.make_slug("class", "/NS/X", disambiguator=1) == "class-NS_X~NS"
    assert slugs.make_slug("class", "/NS/X", disambiguator=2) == "class-NS_X~NS2"
    # back-compat: ns_suffix=True still maps to disambiguator 1
    assert slugs.make_slug("class", "/NS/X", ns_suffix=True) == "class-NS_X~NS"
