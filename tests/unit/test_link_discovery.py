from preapproval_tool.research.link_discovery import (
    find_candidate_subpages,
    same_site_candidates,
    site_root,
)


def test_site_root_strips_to_homepage():
    assert site_root("https://www.brooklynmuseum.org/join") == "https://www.brooklynmuseum.org/"
    assert site_root("https://x.org/a/b?c=1#d") == "https://x.org/"
    assert site_root("not a url") is None


def test_same_site_candidates_keeps_non_keyword_links_for_llm_ranking():
    # '/become-a-member' has no keyword-list hit ('member' != 'membership'),
    # so keyword ranking drops it — but the LLM ranker needs to see it.
    links = [
        "https://ex.org/become-a-member",
        "https://ex.org/about",
        "https://other.com/pricing",
        "https://ex.org/",
    ]
    result = same_site_candidates(links, base_url="https://ex.org", exclude_urls=["https://ex.org/"])
    assert "https://ex.org/become-a-member" in result
    assert "https://ex.org/about" in result
    assert "https://other.com/pricing" not in result  # off-site
    assert "https://ex.org/" not in result  # already fetched


def test_same_site_candidates_dedups_and_excludes_multiple():
    links = ["https://ex.org/a", "https://ex.org/a?x=1", "https://ex.org/b"]
    result = same_site_candidates(
        links, base_url="https://ex.org", exclude_urls=["https://ex.org/b"]
    )
    assert result == ["https://ex.org/a"]


def test_ranks_by_keyword_match_count():
    links = [
        "https://example.org/about",
        "https://example.org/classes/pricing",
        "https://example.org/blog/2020/some-post",
        "https://example.org/contact",
    ]
    result = find_candidate_subpages(
        links, base_url="https://example.org", exclude_url="https://example.org/"
    )
    assert result[0] == "https://example.org/classes/pricing"


def test_excludes_already_fetched_page():
    links = ["https://example.org/", "https://example.org/pricing"]
    result = find_candidate_subpages(
        links, base_url="https://example.org", exclude_url="https://example.org/"
    )
    assert "https://example.org/" not in result
    assert "https://example.org/pricing" in result


def test_excludes_other_domains():
    links = ["https://evil.example.net/pricing", "https://example.org/schedule"]
    result = find_candidate_subpages(
        links, base_url="https://example.org", exclude_url="https://example.org/"
    )
    assert result == ["https://example.org/schedule"]


def test_no_matches_returns_empty():
    links = ["https://example.org/about", "https://example.org/blog"]
    result = find_candidate_subpages(
        links, base_url="https://example.org", exclude_url="https://example.org/"
    )
    assert result == []


def test_excludes_same_page_anchor_of_the_fetched_page():
    """A `#modal-bookclass` anchor on the homepage fetches the exact same
    document as the homepage itself — not a real subpage — caught live
    during Sample 10 verification wasting one of the two bounded attempts."""
    links = ["https://example.org/#modal-bookclass", "https://example.org/classes/"]
    result = find_candidate_subpages(
        links, base_url="https://example.org", exclude_url="https://example.org/"
    )
    assert result == ["https://example.org/classes/"]


def test_respects_limit():
    links = [
        "https://example.org/pricing-a",
        "https://example.org/pricing-b",
        "https://example.org/pricing-c",
    ]
    result = find_candidate_subpages(
        links, base_url="https://example.org", exclude_url="https://example.org/", limit=2
    )
    assert len(result) == 2
