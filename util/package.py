"""Representation of an Android package."""

from typing import Any, List, Mapping, Set

from util.parse import ParsedJSON
from util.recursive_search import GithubLinkSearch


class Package(object):
    """Representation of an Android package.

    A Package is used to match a package in open source Github repositories to
    a package on Google Play.

    :param str package_name: Package name as defined in Android manifest file
        and used as identifier on Google Play.
    :param ParsedJSON google_play_details: Details from Google Play parsed from
        JSON.
    """
    def __init__(self, package_name: str, google_play_details: ParsedJSON):
        self.package_name = package_name
        self.play_info = {'details': google_play_details}
        self.github_info = {}
        self.repos = []

    def is_known_package(self, known_packages: Mapping[str, Any]) -> bool:
        """Test if name of this package is in packages.

        :param Mapping[str, Any] known_packages: Dict with package names as
            keys.
        :returns bool: True if self.package_name is a key in known_packages,
            False otherwise.
        """
        return self.package_name in known_packages

    def search_github_links(self) -> Set[str]:
        """Search package details for Github links.

        Links to Github are stored with their two initial path segments that
        potentially equal to a repository identifier.

        Examples:
            https://github.com/blog/category/engineering
            --> blog/category

            https://github.com/google/battery-historian/blob/master/README.md
            --> google/battery-historian

        :returns Set[str]: Set of first two path segments of links to Github
            found in Google Play Details for this package.
        """
        search = GithubLinkSearch()
        search.search(self.play_info['details'])
        self.play_info.update({
                'search_results': search.results,
                'github_links': {r['match'] for r in search.results}
                })
        return self.play_info['github_links']

    def set_github_repos(self, known_packages: Mapping[str, List[str]]):
        """Set repositories stored for this package name in packages.

        :param Dict[str, List[str]] known_packages: A mapping from package name
            to list of Github repositories that contain a manifest file for the
            key.
        """
        self.github_info['repos'] = known_packages.get(self.package_name, [])

    def has_unique_github_repo(self) -> bool:
        """Test if only one repository on GitHub mentions this package."""
        return len(set(self.github_info['repos'])) == 1

    def has_github_links(self) -> bool:
        """Test if Google Play details contain at least one link to Github."""
        return len(self.play_info['github_links']) > 0

    def has_repo_links(self) -> bool:
        """Test if Google Play details contain at least one link to a matching
        repo.
        """
        return len(self.repos) > 0

    def has_too_many_repo_links(self) -> bool:
        """Test if Google Play details contain more than one repo link."""
        return len(self.repos) > 1

    def _link_is_valid_repo(self, link: str) -> bool:
        """Test if potential repository link is valid.

        :returns bool: True if repository described by link contains an
            Android manifest file for this package.
        """
        return link in self.github_info['repos']

    def match_repos_to_links(self):
        """Find repositories with link from Google Play that also contain a
        manifest for the same package name.
        """
        self.repos += list(filter(
                self._link_is_valid_repo,
                self.play_info['github_links']))
