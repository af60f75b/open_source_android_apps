"""GitHub API wrapper that adheres to rate limit.

Access to Github API v3 is rate limited. All API requests from
this wrapper automatically wait for reset if rate limit is reached. This
is achieved by overriding the get method in GitHubSession.

Rate limit data is read from headers of last response if available. If
there is not response available, rate limit information is requested from
the /rate_limit endpoint of the Github API v3. For more information see
https://developer.github.com/v3/rate_limit/
"""

from datetime import datetime
import logging
from github3 import GitHub
from github3.models import GitHubCore
from github3.session import GitHubSession
from requests.structures import CaseInsensitiveDict
from urllib.parse import urlparse
import time


__log__ = logging.getLogger(__name__)


class RateLimitedGitHubSession(GitHubSession):
    """Provices functionality to avoid rate limit of Github API.

    Use this class instead of GitHubSession to avoid rate limits and abuse
    detection.

    Also provides self.suggested_time_between_requests in order to
    proactively avoid abuse detection: Consider sleeping for suggested
    time between requests.
    """
    RATELIMIT_LIMIT_HEADER = 'X-RateLimit-Limit'
    RATELIMIT_REMAINING_HEADER = 'X-RateLimit-Remaining'
    RATELIMIT_RESET_HEADER = 'X-RateLimit-Reset'

    CORE_RESOURCE = 'core'
    SEARCH_RESOURCE = 'search'
    GRAPHQL_RESOURCE = 'graphql'  # Unused by github3.py

    DEFAULT_SLEEP_PERIOD = 1

    def __init__(self):
        super(RateLimitedGitHubSession, self).__init__()
        self._ratelimit_cache = {}
        self.suggested_time_between_requests = self.DEFAULT_SLEEP_PERIOD

    def _fill_ratelimit_cache(self) -> dict:
        """Fills rate limit cache with data from server."""
        response = self.get(self.build_url('rate_limit'))
        if response.status_code == 200 and response.content:
            json = response.json()
            if 'resources' in json:
                self._ratelimit_cache = json['resources']
        else:
            __log__.critical('Cannot fill ratelimit cache')

    def _has_ratelimit_headers(self, headers: CaseInsensitiveDict) -> bool:
        """Test if rate limit headers are present.

        :param requests.structures.CaseInsensitiveDict headers:
            Headers from response.
        :returns bool:
            True if all necessary headers are present, otherwise False.
        """
        return (
                self.RATELIMIT_LIMIT_HEADER in headers and
                self.RATELIMIT_REMAINING_HEADER in headers and
                self.RATELIMIT_RESET_HEADER in headers)

    def _cache_ratelimit_headers(
            self, headers: CaseInsensitiveDict,
            resource: str=CORE_RESOURCE) -> dict:
        """Cache rate limit information from response headers.

        :param requests.structures.CaseInsensitiveDict headers:
            Headers from response.
        :param str resource:
            Name of resource to get rate limit for. Either CORE_RESOURCE,
            SEARCH_RESOURCE, or GRAPHQL_RESOURCE.
        :returns dict:
            Dictionary containing remaining rate limit, full rate limit, and
            reset time as POSIX timestamp.  For more information see
            https://developer.github.com/v3/rate_limit/
        """
        if not self._ratelimit_cache:
            self._ratelimit_cache = {}
        if self._has_ratelimit_headers(headers):
            self._ratelimit_cache[resource] = {
                    'limit': headers.get(self.RATELIMIT_LIMIT_HEADER),
                    'remaining': headers.get(self.RATELIMIT_REMAINING_HEADER),
                    'reset': headers.get(self.RATELIMIT_RESET_HEADER)
                    }

    def _get_ratelimit(self, resource: str=CORE_RESOURCE):
        """Get ratelimit information from cache or server.

        :param str resource:
            Name of resource to get rate limit for. Either CORE_RESOURCE,
            SEARCH_RESOURCE, or GRAPHQL_RESOURCE.
        :returns dict:
            Dictionary containing remaining rate limit, full rate limit, and
            reset time as POSIX timestamp.  For more information see
            https://developer.github.com/v3/rate_limit/
        """
        if not (self._ratelimit_cache and resource in self._ratelimit_cache):
            self._fill_ratelimit_cache()
        return self._ratelimit_cache[resource]

    def _wait_for_ratelimit(self, resource: str=CORE_RESOURCE):
        """Waits until ratelimit refresh if necessary.

        Rate limit is read from headers of last response if this class has
        a `last_response` member.

        :param str resource:
            Name of resource to get rate limit for. Either CORE_RESOURCE,
            SEARCH_RESOURCE, or GRAPHQL_RESOURCE.
        """
        ratelimit = self._get_ratelimit(resource)
        if int(ratelimit.get('remaining', '0')) < 1:
            reset = datetime.utcfromtimestamp(int(ratelimit.get('reset', '0')))
            delta = reset - datetime.utcnow()
            wait_time = int(delta.total_seconds()) + 2
            if wait_time > 0:
                __log__.info(
                        'Rate limit reached. Wait for %d sec until %s',
                        wait_time, reset)
                time.sleep(wait_time)

    def _resource_from_url(self, url: str) -> str:
        """Extract rate limited resource from url.

        :param str url:
            URL to check.
        :returns str:
            SEARCH_RESOURCE if first part of path is 'search',
            otherwise CORE_RESOURCE.
        """
        # This should check 'Accept' header in case github3.py gains
        # functionality to query graphql.
        path_frags = urlparse(url).path.split('/')
        if len(path_frags) > 1 and path_frags[1] == self.SEARCH_RESOURCE:
            return self.SEARCH_RESOURCE
        else:
            return self.CORE_RESOURCE

    def request(self, method, url, *args, **kwargs):
        """Wrapper for GitHubSession.request() to avoid rate limits.

        Also catches abuse errors (status 403) and retries in case of
        connection errors.
        """
        retry_after_header = 'Retry-After'
        resource = self._resource_from_url(url)
        if url is not self.build_url('rate_limit'):
            self._wait_for_ratelimit(resource=resource)
        while True:
            try:
                response = super(RateLimitedGitHubSession, self).request(
                        method, url, *args, **kwargs)
                if (response is not None and response.status_code == 403 and
                        retry_after_header in response.headers):
                    retry_after = int(response.headers[retry_after_header])
                    __log__.warn(
                            'Status %d: %s', response.status_code,
                            response.json())
                    __log__.info('Retry after: %d', retry_after)
                    self.suggested_time_between_requests *= 2
                    time.sleep(retry_after + self.DEFAULT_SLEEP_PERIOD)
                elif response is not None and response.status_code == 403:
                    __log__.error(
                            'Status %d: %s', response.status_code,
                            response.json())
                    self._fill_ratelimit_cache()
                    self._wait_for_ratelimit(resource=resource)
                else:
                    break
            except ConnectionError as e:
                __log__.exception(e)
                __log__.critical(
                        'Re-running request might lead to skipped '
                        'data. Do it anyway after %d seconds.',
                        self.DEFAULT_SLEEP_PERIOD)
                time.sleep(self.DEFAULT_SLEEP_PERIOD)
        self._cache_ratelimit_headers(response.headers, resource)
        return response


class RateLimitedGitHub(GitHub):
    """Rate limited version of GitHub.

    Wrapper for github3.GitHub to actively avoid running into rate limits
    and waiting for suggested time if abuse detection is triggered.
    """
    def __init__(self, login='', password='', token=''):
        GitHubCore.__init__(self, {}, RateLimitedGitHubSession())
        if token:
            self.login(login, token=token)
        elif login and password:
            self.login(login, password)
