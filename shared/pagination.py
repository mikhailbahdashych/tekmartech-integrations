"""Common pagination helpers for MCP server tool implementations.

GitHub uses Link header pagination. This module parses the standard HTTP
Link header format to extract pagination URLs.
"""

from __future__ import annotations

import re

# Matches individual link entries: <URL>; rel="relation"
_LINK_PATTERN = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')


def parse_link_header(link_header: str) -> dict[str, str]:
    """Parse an HTTP Link header into a dict of {relation: url}.

    Args:
        link_header: The raw Link header value.
            Example: '<https://api.github.com/orgs/foo/members?page=2>; rel="next",
                      <https://api.github.com/orgs/foo/members?page=5>; rel="last"'

    Returns:
        A dict mapping relation names to URLs.
            Example: {"next": "https://...?page=2", "last": "https://...?page=5"}
    """
    return {rel: url for url, rel in _LINK_PATTERN.findall(link_header)}


def get_next_url(link_header: str | None) -> str | None:
    """Extract the 'next' page URL from a Link header.

    Args:
        link_header: The raw Link header value, or None if absent.

    Returns:
        The URL for the next page, or None if there is no next page.
    """
    if not link_header:
        return None
    links = parse_link_header(link_header)
    return links.get("next")
