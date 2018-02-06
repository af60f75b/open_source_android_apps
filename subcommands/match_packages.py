"""Match package names to Github repositories.

Use -h or --help for more information.
"""

import argparse
import csv
import json
import logging
import os
import sys
from typing import IO, Iterator, List, Tuple

from util.github_repo import RepoVerifier
from util.package import Package
from util.parse import parse_package_details, parse_package_to_repos_file


__log__ = logging.getLogger(__name__)


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Define commandline arguments."""
    parser.add_argument(
        'DETAILS_DIRECTORY',
        type=str,
        help='Directory containing JSON files with details from Google Play.')
    parser.add_argument(
        '-p', '--package_list',
        default=sys.stdin,
        type=argparse.FileType('r'),
        help='''CSV file that matches package names to repositories.
            The file needs to contain a column `package` and a
            column `all_repos`. `all_repos` contains a comma
            separated string of Github repositories that include an
            AndroidManifest.xml file for package name in column
            `package`. Default: stdin.
            ''')
    parser.add_argument(
        '-o', '--out', default=sys.stdout, type=argparse.FileType('w'),
        help='File to write CSV output to. Default: stdout')
    parser.set_defaults(func=_main)


def deduplicate(repo_names: List[str], repo_verifier: RepoVerifier) -> str:
    """Deduplicate repositories by popularity.

    Fetches meta data from Github and filters out most popular repository.
    Filters are applied in this order:
        - Repositories that are not forks themselves
        - Repositories with most forks
        - Repositories with most watchers
        - Repositories with most subscribers

    :param List[str] repo_names:
        List of repository names to filter.
    :param RepoVerifier repo_verifier:
        Instance to fetch meta data from Github.
    :returns str:
        Full name of most popular repository or None if no unique most popular
        repo exists.
    """
    # Return early if possible to avoid unnecessary API calls
    if len(repo_names) == 1:
        return repo_names[0]['full_name']

    # Download meta data from Github
    repos = [
            repo_verifier.get_repo_info(repo_name)
            for repo_name in repo_names]
    # Deduplicate by canonical repo name and filter out None
    repos = {repo['full_name']: repo for repo in repos if repo}.values()

    if len(repo_names) == 1:
        return repo_names[0]['full_name']

    repos = list(filter(lambda r: not r['fork'], repos))

    for metric in ['forks_count', 'watchers_count', 'subscribers_count']:
        if len(repos) == 1:
            return repos[0]['full_name']
        if not repos:
            break
        max_value = max(repos, key=lambda r: r[metric])
        repos = list(filter(lambda r: r[metric] == max_value, repos))

    if len(repos) == 1:
        return repos[0]['full_name']
    return None


def match_play_and_github(
        package_to_repo: IO[str], details_dir: str,
        repo_verifier: RepoVerifier) -> Iterator[Tuple[str, str]]:
    """Match Android apps on Google Play with their repositories on Github.

    :param IO[str] input_file:
        CSV file to parse.
        The file needs to contain a column `package` and a column
        `all_repos`. `all_repos` contains a comma separated string of
        Github repositories that include an AndroidManifest.xml file for
        package name in column `package`.
    :param str details_dir:
        Name of directory to include JSON files from. Filenames in this
        directory need to have .json extension. Filename without extension is
        assumed to be package name for details contained in file.
    :param util.repo_verifier.RepoVerifier:
        Instance of RepoVerifier to use for Github API v3 access.
    :returns Iterator[Tuple[str, str]]:
        An iterator over package name and repository name that match.
    """
    stats = {
            'all': 0,
            'unknown': 0,
            'valid': 0,
            'no_github_link': 0,
            'no_github_link_but_unique_popular': 0,
            'unique_repo': 0,
            'no_repo': 0,
            'too_many_repos': 0,
            }
    packages = parse_package_to_repos_file(package_to_repo)

    for package_name, package_details in parse_package_details(details_dir):
        stats['all'] += 1
        package = Package(package_name, package_details)

        if not package.is_known_package(packages):
            __log__.debug('"%s" is not a known package', package_name)
            stats['unknown'] += 1
            continue

        package.search_github_links()
        # TODO: Parse gradle files for Android ID
        package.set_github_repos(packages)
        package.match_repos_to_links()
        # TODO: Parse gradle files for android application

        is_unique_repo = package.has_unique_github_repo()

        if not package.has_github_links() and not is_unique_repo:
            __log__.debug(
                    '"%s" does not link to Github and has these %d repos '
                    'on Github: %s',
                    package_name,
                    len(package.github_info['repos']),
                    package.github_info['repos'])
            stats['no_github_link'] += 1
            # Try deduplication by popularity
            most_popular = deduplicate(
                    package.github_info['repos'], repo_verifier)
            if most_popular:
                stats['no_github_link_but_unique_popular'] += 1
                __log__.debug(
                        '"%s" is most popular repo for %s',
                        most_popular, package_name)
                yield package_name, most_popular
        elif not package.has_repo_links() and not is_unique_repo:
            __log__.debug(
                    '"%s" does not link to valid repo (%s) and has these %d '
                    'repos on Github: %s',
                    package_name, package.play_info['github_links'],
                    len(package.github_info['repos']),
                    package.github_info['repos'])
            stats['no_repo'] += 1
        elif package.has_too_many_repo_links() and not is_unique_repo:
            __log__.debug(
                    '"%s" has %d repo links', package_name,
                    len(package.repos))
            stats['too_many_repos'] += 1
        else:
            if is_unique_repo:
                stats['unique_repo'] += 1
                repo = package.github_info['repos'][0]
            else:
                repo = package.repos[0]
            stats['valid'] += 1
            yield package_name, repo

    # TODO: Above steps should be performed independently and sequentially.
    #       Move them out into separate generators.
    #       The idea is:
    #        - Gather data and write it to csv file
    #           + get links from google play
    #           + get repositories for packages
    #           + get gradle files
    #              * Application/library definition
    #              * Android ID
    #        - Canonicalize data and write it back to csv file.
    #           + links on google play need to be canonicalized (do they?)
    #        - ...
    __log__.debug(json.dumps(stats, indent=2))


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    __log__.debug('Reading from %s', args.package_list.name)
    csv_writer = csv.writer(args.out)
    repo_verifier = RepoVerifier(token=os.getenv('GITHUB_AUTH_TOKEN'))
    for row in match_play_and_github(
            args.package_list,
            args.DETAILS_DIRECTORY,
            repo_verifier):
        csv_writer.writerow(row)
