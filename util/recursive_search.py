"""Recursively search parsed JSON."""

import re
from typing import Mapping, Sequence, Text, Tuple, Union
from typing.re import Pattern
from util.parse import ParsedJSON

PathSegment = Union[int, str]
Path = Tuple[PathSegment, ...]


class RecursiveSearch:
    """Recursively search an object parsed from JSON.

    :param Pattern pattern: Compiled regular expression to search for.
    """

    def __init__(self, pattern: Pattern):
        self.pattern = pattern
        self.results = []

    def search(self, haystack: ParsedJSON, path: Path=()):
        """Search haystack for self.pattern.

        Stores matches in self.results. Each match contains a dict containing
        `path` of type `Path` and `match` of type `str`.

        :param ParsedJSON haystack: Parsed JSON to search for self.pattern.
            Accepts all types json.JSONDecoder may return.
        :param Path path: Path of haystack from JSON root.
        """
        if isinstance(haystack, dict):
            self._search_dict(haystack, path)
        elif isinstance(haystack, list):
            self._search_list(haystack, path)
        elif isinstance(haystack, str):
            self._search_str(haystack, path)
        # Ignore numbers, bool and None since they cannot contain a link.

    def _search_dict(self, d: Mapping[Text, ParsedJSON], path: Path):
        for k, v in d.items():
            self.search(v, path + (k,))

    def _search_list(self, l: Sequence, path: Path):
        for index, item in enumerate(l):
            self.search(item, path + (index,))

    def _search_str(self, s: Text, path: Path):
        for match in re.findall(self.pattern, s):
            self.results.append({
                'path': path,
                'match': match
                })


class GithubLinkSearch(RecursiveSearch):
    """Recursively search an object parsed from JSON for links to Github.

    Match and return first two path segments.

    Also matches links if slashes are URL encoded.

    Examples:
        https://github.com/blog/category/engineering
        --> blog/category

        https://github.com/google/battery-historian/blob/master/README.md
        --> google/battery-historian

        https:%2F%2Fgithub.com%2Fblog%2Fcategory%2Fengineering
        --> blog/category
    """

    # Match both normal and encoded slashes (%2F).
    GITHUB_LINK_PATTERN = re.compile(
            r'(?i)github\.com(\/|%2F)([a-z0-9_-]+)\1([a-z0-9_-]+)')
    # r'github\.com\/([A-Za-z0-9_-]*\/[A-Za-z0-9_-]*)')

    def __init__(self):
        RecursiveSearch.__init__(self, GithubLinkSearch.GITHUB_LINK_PATTERN)

    def _search_str(self, s: Text, path: Path):
        """Construct match from groups in GITHUB_LINK_PATTERN."""
        for groups in re.findall(self.pattern, s):
            # groups[0] contains either "/" or "%2F" and can be discarded.
            self.results.append({
                'path': path,
                'match': '{1}/{2}'.format(*groups)
                })
