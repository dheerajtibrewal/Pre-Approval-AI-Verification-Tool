from preapproval_tool.evaluation.text_utils import is_quote_grounded, strip_markdown


def test_strip_markdown_removes_emphasis_and_headings():
    assert strip_markdown("**30-Minute Group - $80**") == "30-Minute Group - $80"
    assert strip_markdown("# Pricing") == "Pricing"
    assert strip_markdown("[GallopNYC](https://gallopnyc.org)") == "GallopNYC"


def test_quote_grounded_true_for_exact_substring():
    page = "Our lessons are available for children and adults of all skill levels."
    assert is_quote_grounded("adults of all skill levels", page)


def test_quote_grounded_tolerates_markdown_formatting_difference():
    page = "**30-Minute Group - $80**\n\nMore text here."
    assert is_quote_grounded("30-Minute Group - $80", page)


def test_quote_grounded_false_for_fabricated_text():
    page = "GallopNYC offers recreational riding lessons to the public."
    assert not is_quote_grounded("Membership costs $500 per year", page)


def test_quote_grounded_false_for_empty_inputs():
    assert not is_quote_grounded("", "some page text")
    assert not is_quote_grounded("some quote", "")
