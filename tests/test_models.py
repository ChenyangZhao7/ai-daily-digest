from src.models import normalize_url, make_id


def test_normalize_url_strips_tracking_and_fragment():
    assert normalize_url("https://Example.com/a/?utm_source=x&id=7#frag") == "https://example.com/a?id=7"


def test_normalize_url_drops_trailing_slash():
    assert normalize_url("https://a.com/x/") == "https://a.com/x"


def test_make_id_is_stable_across_url_variants():
    assert make_id("https://a.com/x/?utm_medium=y") == make_id("https://a.com/x")
