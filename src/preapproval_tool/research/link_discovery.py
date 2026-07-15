"""Finds likely subpages (pricing/schedule/classes pages) worth a bounded
follow-up fetch when the homepage alone didn't answer a fee/price/schedule
criterion. Generic across every category — driven by keyword matching, not
per-category logic — so a new checklist config needs no changes here.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Keywords are intentionally generic (not tied to any one category) since the
# same "is there a subpage with more detail" question applies whether the
# missing fact is a class fee, a product price, or a membership rate.
_SUBPAGE_KEYWORDS = (
    "class", "pricing", "price", "fee", "membership", "program",
    "schedule", "rate", "tuition", "cost", "join", "enroll",
)


def site_root(url: str) -> str | None:
    """The scheme+host homepage for a URL (https://host/), or None if the URL
    has no usable host. Used to back off to a provider's main site when the
    exact deep link on the application form is dead."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/"


def _same_site(candidate: str, base_netloc: str) -> bool:
    netloc = urlparse(candidate).netloc.lower()
    base = base_netloc.lower()
    return netloc == base or netloc.endswith("." + base) or base.endswith("." + netloc)


def page_identity(url: str) -> str:
    """A same-page anchor (`#modal-bookclass`) or query string fetches the
    exact same document as its base URL — not a different page worth a
    follow-up fetch — so identity is compared ignoring fragment and query.
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


# Back-compat alias for existing internal callers.
_page_identity = page_identity


def same_site_candidates(
    links: list[str], *, base_url: str, exclude_urls: list[str]
) -> list[str]:
    """Every distinct same-site http(s) URL in `links`, minus the pages already
    fetched (compared ignoring fragment/query). Unlike find_candidate_subpages
    this applies NO keyword filter — an LLM ranker downstream can recognise a
    good link (e.g. '/become-a-member') that keyword matching would miss, so it
    needs the unfiltered set to choose from.
    """
    base_netloc = urlparse(base_url).netloc
    seen: set[str] = {_page_identity(u) for u in exclude_urls}
    out: list[str] = []
    for link in links:
        if not link.startswith(("http://", "https://")):
            continue
        identity = _page_identity(link)
        if identity in seen:
            continue
        if not _same_site(link, base_netloc):
            continue
        seen.add(identity)
        out.append(link)
    return out


def find_candidate_subpages(
    links: list[str], *, base_url: str, exclude_url: str, limit: int = 2
) -> list[str]:
    """Returns up to `limit` same-site URLs whose path/text looks likely to
    carry the missing fact, ranked by keyword-match count. Never returns the
    page already fetched (including same-page anchors/query variants of it),
    and never leaves the provider's own site.
    """
    base_netloc = urlparse(base_url).netloc
    scored: list[tuple[int, str]] = []
    seen: set[str] = {_page_identity(exclude_url)}

    for link in links:
        identity = _page_identity(link)
        if identity in seen:
            continue
        if not link.startswith(("http://", "https://")):
            continue
        if not _same_site(link, base_netloc):
            continue
        seen.add(identity)

        haystack = link.lower()
        score = sum(1 for kw in _SUBPAGE_KEYWORDS if kw in haystack)
        if score > 0:
            scored.append((score, link))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [url for _, url in scored[:limit]]
