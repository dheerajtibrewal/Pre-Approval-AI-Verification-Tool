"""The LLM link ranker only ever re-orders real, already-discovered URLs — it
never fetches or invents. These tests mock the LLM call so they're offline."""

from unittest.mock import patch

from preapproval_tool.research import link_ranker


def test_picks_the_indices_the_model_returns_in_order():
    with patch.object(link_ranker, "structured_completion", return_value={"indices": [2, 0]}):
        result = link_ranker.rank_links(
            "membership fee",
            ["https://ex.org/a", "https://ex.org/b", "https://ex.org/become-a-member"],
            limit=2,
        )
    assert result == ["https://ex.org/become-a-member", "https://ex.org/a"]


def test_ignores_out_of_range_or_duplicate_indices():
    with patch.object(link_ranker, "structured_completion", return_value={"indices": [99, 0, 0]}):
        result = link_ranker.rank_links("fee", ["https://ex.org/a", "https://ex.org/b"], limit=2)
    assert result == ["https://ex.org/a"]


def test_returns_none_when_model_finds_nothing_relevant():
    with patch.object(link_ranker, "structured_completion", return_value={"indices": []}):
        assert link_ranker.rank_links("fee", ["https://ex.org/a"]) is None


def test_returns_none_on_llm_error_so_caller_falls_back_to_keywords():
    with patch.object(link_ranker, "structured_completion", side_effect=RuntimeError("boom")):
        assert link_ranker.rank_links("fee", ["https://ex.org/a"]) is None


def test_empty_candidate_list_returns_empty_without_calling_the_model():
    with patch.object(link_ranker, "structured_completion", side_effect=AssertionError("should not be called")):
        assert link_ranker.rank_links("fee", []) == []
