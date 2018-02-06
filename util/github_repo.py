"""Retrieve information about a repository from Github.

Example:
    >>> v = RepoVerifier()
    >>> r = v.get_repo('python/cpython')
    >>> r.full_name
    'python/cpython'
    >>> r.description
    'The Python programming language'
    >>> r.count_commits()
    100334
    >>> r.meta_data
    {
        'id': 81598961,
        'name': 'cpython',
        'full_name': 'python/cpython',
        'description': 'The Python programming language',
        'size': 222614,
        'archived': False,
        'fork': False,
        'private': False,
        'language': 'Python',
        'created_at': '2017-02-10T19:23:51+00:00',
        'pushed_at': '2017-11-03T15:43:31+00:00',
        'updated_at': '2017-11-03T15:44:13+00:00',
        'owner_login': 'python',
        'owner_id': 1525981,
        'owner_type': 'Organization',
        'homepage': 'https://www.python.org/',
        'default_branch': 'master',
        'watchers_count': 14032,
        'stargazers_count': 14032,
        'forks_count': 3106,
        'subscribers_count': 730,
        'network_count': 3106,
        'has_pages': False,
        'has_wiki': False,
        'has_projects': False,
        'has_downloads': True,
        'has_issues': False,
        'parent_id': None,
        'source_id': None
    }
"""

import logging
import re
from github3.repos.repo import Repository
from github3.models import GitHubError
from typing import Any, Callable, Tuple
from urllib.parse import urlparse, parse_qs
from .parse import ParsedJSON
from .ratelimited_github import RateLimitedGitHub


__log__ = logging.getLogger(__name__)


class Repo(Repository):
    """Selection of information about repository.

    Relevant pieces of information are gathered in property `meta_data`.
    """
    @property
    def meta_data(self):
        """A flat selection of relevant meta data."""
        repo = self
        repo_json = self.to_json()
        return {
            'id': repo.id,
            'name': repo.name,
            'full_name': repo.full_name,
            'description': repo.description,
            'size': repo.size,

            'private': repo.private,
            'fork': repo.fork,
            'archived': repo_json['archived'],

            'created_at': repo.created_at.isoformat(),
            'updated_at': repo.updated_at.isoformat(),
            'pushed_at': repo.pushed_at.isoformat(),

            'language': repo.language,
            'default_branch': repo.default_branch,
            'homepage': repo.homepage,

            'forks_count': repo.forks_count,
            'stargazers_count': repo_json['stargazers_count'],
            'subscribers_count': repo_json['subscribers_count'],
            'watchers_count': repo_json['watchers_count'],
            'network_count': repo_json['network_count'],

            'has_downloads': repo.has_downloads,
            'has_issues': repo.has_issues,
            'has_pages': repo_json['has_pages'],
            'has_projects': repo_json['has_projects'],
            'has_wiki': repo.has_wiki,

            'owner_id': repo.owner.id if repo.owner else -1,
            'owner_login': repo.owner.login if repo.owner else None,
            'owner_type': repo.owner.type if repo.owner else None,

            # Repo this repo is forked from
            'parent_id': repo.parent.id if repo.parent else -1,
            # Root of fork network
            'source_id': repo.source.id if repo.source else -1,
        }

    @staticmethod
    def _parse_num_pages(url: str) -> int:
        """Extract number of result pages from URL.

        :param str url:
            URL to parse `page` query part from.
        :returns int:
            Number of result pages if `page` argument exists, 1 otherwise.
        """
        query_params = parse_qs(urlparse(url).query)
        page_arg = query_params.get('page', ['1'])
        if len(page_arg) < 1:
            return 1
        return int(page_arg[0])

    def has_n_commits(self, n_commits: int) -> bool:
        """Test if repository has at least n_commits.

        :param int n_commits:
            Number of commits that repository should have.
        :returns bool:
            True if repository has at least n_commits, otherwise False.
        """
        return self.count_commits(stop_at=n_commits) >= n_commits

    def count_commits(self, stop_at: int = -1):
        """Count commits in main branch of this repository.

        This takes at most two requests to Github API.

        :param int stop_at:
            Stop counting if repository has at least stop_at commits.
            This safes at most two requests. Negative values mean that the
            total amount is returned. Default: -1.
        :returns int:
            Number of commits N in main branch of this repository, if
            stop_at < 0 OR N <= stop_at.  Otherwise X with
            0 < stop_at <= X <= N.
        """
        if stop_at == 0:
            return 0
        page_iterator = self.iter_commits(self.default_branch)
        # Perform actual HTTP request for first page
        try:
            page_iterator.next()
        except GitHubError as e:
            if e.code == 409:  # 409 Conflict
                # This is an empty repository
                return 0
            raise e

        last_link = page_iterator.last_response.links.get('last', {})
        last_rel = last_link.get('url', '')
        num_pages = self._parse_num_pages(last_rel)
        count_per_page = page_iterator.params['per_page']

        if num_pages == 1 or 0 < stop_at <= count_per_page:
            last_page = page_iterator.last_response
        else:
            # Use get method of iterator to read rate limit in response headers
            last_page = page_iterator._get(
                    last_rel, headers=page_iterator.headers)

        count_last_page = len(page_iterator._get_json(last_page))

        return count_per_page * (num_pages - 1) + count_last_page


class RepoVerifier(RateLimitedGitHub):
    """Download information about repositories from Github.

    Help repository deduplication with information on canonical
    repository names, forks, and statistics.

    :param str token:
        Github authentication token. Get one for your account at
        https://github.com/settings/tokens
    """
    FULL_NAME_PATTERN = re.compile(r'^([a-z0-9-]+)\/([a-z0-9_\.-]+)$', re.I)

    def get_repo(self, full_name: str) -> Repo:
        """Get repository with full_name.

        :param str full_name:
            Identifier of the repository on Github consisting of
            <owner_login>/<repo_name>.
        :raises ValueError:
            if owner and repo cannot be extracted from full name.
        :returns Repo:
            Repository identified by full_name.
        """
        owner, name = self.full_name_to_parts(full_name)
        repo = self.repository(owner, name)
        return Repo(repo.to_json(), repo._session) if repo else None

    def get_repo_info(self, full_name: str) -> ParsedJSON:
        """Retrieve information on repository from Github.

        :param str full_name:
            Identifier of the repository on Github consisting of
            <owner_login>/<repo_name>.
        :raises ValueError:
            if owner and repo cannot be extracted from full name.
        :returns ParsedJSON: TODO
        """
        repo = self.get_repo(full_name)
        return repo.meta_data if repo else None

    @staticmethod
    def full_name_to_parts(full_name: str) -> Tuple[str, str]:
        """Extract owner and repository name from full name.

        :param str full_name:
            Full name identifier of Github repository, consisting
            of owner login and repository name, e.g. python/cpython
        :raises ValueError:
            if owner and repo cannot be extracted from full name.
        :returns Tuple[str, str]:
            A tuple of owner login and repository name.
        """
        match = RepoVerifier.FULL_NAME_PATTERN.match(full_name)
        if match:
            return match.groups()
        raise ValueError(
                '{} is not a valid name of a Github repository'.format(
                    full_name))

    def catch_renamed_repo(
            self, repo_name: str,
            try_fn: Callable[[str], Any]) -> Tuple[str, Any]:
        """Execute try_fn dynamically handling renamed repositories.

        When using Github's search API, unknown repository names result in
        HTTP status 422. This happens also for renamed repositories. This
        method tries executing try_fn(repo_name). If status 422 is
        encountered, the new name of the repository is requested from Github.
        In case a new name is found, try_fn(new_name) is tried again.

        In case Github does not return a repository for the name, (None, None)
        is returned.

        Other exceptions are passed through.

        :param str repo_name:
            Known name of repository.
        :param Callable[[str], Any] try_fn:
            Function to execute for repository name. Takes name of repository
            as argument.
        :returns Tuple:
            a tuple of the canonical repository name and whatever try_fn
            returns if a repository is found. Otherwise (None, None).
        """
        while repo_name:
            try:
                result = try_fn(repo_name)
                return repo_name, result
            except GitHubError as error:
                if error.code == 422:  # Validation Failed
                    # Likely a repo name that does not exist anymore
                    parts = RepoVerifier.full_name_to_parts(repo_name)
                    repo = self.repository(*parts)
                    if not repo:
                        __log__.info('Repo does not exist: %s', repo_name)
                        return None, None
                    elif repo.full_name is not repo_name:
                        __log__.info(
                            'Repo was moved: %s -> %s', repo_name,
                            repo.full_name)
                        repo_name = repo.full_name  # Try with new name
                    else:
                        __log__.exception(error)
                        raise error


if __name__ == '__main__':
    import doctest
    doctest.testmod()
