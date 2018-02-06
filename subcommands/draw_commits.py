"""Draw a random sample of commits from GitHub

For each package name in PACKAGE_LIST search the respective repository for a
manifest file with given package name. Total population of commits consists of
all commits changing files under same path as the manifest files.

Repositories can be filitered by a minimum number of commits requirement.

Use -h or --help for more information.
"""
import argparse
import csv
import logging
import os
import random
import sys
from typing import IO, Iterator, Set, Tuple
from github3.repos.repo import Repository
from github3.repos.commit import RepoCommit
from util.github_repo import RepoVerifier


__log__ = logging.getLogger(__name__)


MANIFEST_SEARCH = 'repo:{} filename:AndroidManifest.xml package="{}"'
OUTPUT_FIELDNAMES = ['Repository', 'Commit', 'Message']


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Add arguments to parser."""
    parser.add_argument(
        '-p', '--package_list', default=sys.stdin, type=argparse.FileType('r'),
        help='''CSV file that lists package name and repository name in
            a column each. The file should not have a header.
            Default: stdin.''')
    parser.add_argument(
        '-c', '--min_commits', default=2, type=int,
        help='''Minimum number of commits in main branch for repository
            to be cloned. CSV file needs to have column commit_count for
            this to work.''')
    parser.add_argument(
        '-s', '--sample_size', default=5000, type=int,
        help='Number of commits to draw in total. Default: 5000.')
    parser.add_argument(
        '-o', '--outfile', default=sys.stdout, type=argparse.FileType('w'),
        help='Path to store output file at. Default: stdout')
    parser.set_defaults(func=_main)


def find_commits(
        github: RepoVerifier, repo: Repository, package_name: str) -> Iterator[
            Tuple[Repository, RepoCommit]]:
    """Find commits in repository.

    Only commits which include changes under a path of an Android manifest file
    for package_name are included.

    :param RepoVerifier github:
        API instance to contact Github.
    :param Repository repo:
        Repository to get commits from.
    :param str package_name:
        Package name to restrict commits for. Only paths with a fitting
        manifest file are considered.
    :returns Iterator[Tuple[Repository, RepoCommit]]:
        Iterator of tuples identifying a commit by repository and commit.
    """
    query = MANIFEST_SEARCH.format(repo.full_name, package_name)
    for manifest in github.search_code(query):
        path = os.path.dirname(manifest.path)
        if repo != manifest.repository:
            __log__.warning(
                'Repository in search result does not match: %s != %s',
                repo, manifest.repository)
        for commit in repo.iter_commits(path=path):
            yield repo, commit


def collect_commits(
        package_list: IO[str], min_commits: int,
        github: RepoVerifier) -> Set[Tuple[Repository, RepoCommit]]:
    """Collect commits from repositories.

    Only commits changing a subpath which has a manifest file for packages
    in package_list are considerd.

    :param IO[str] package_list:
        Readable file match package names to repositories.
    :param int min_commits:
        Minimum number of commits in a repositoriy to be considered.
    :param RepoVerifier github:
        Instance to access Github API v3.
    :returns Set[Tuple[Repository, RepoCommit]]:
        Set of commits identified by repository and commit.
    """
    package_reader = csv.DictReader(
        package_list, fieldnames=['package_name', 'repo_name'])
    commits = set()
    for package in package_reader:
        package_name = package['package_name']
        # Get latest repository name to avoid broken search queries.
        repo = github.get_repo(package['repo_name'])
        if not repo:
            __log__.warning(
                'Cannot access repository: %s', package['repo_name'])
        elif repo.has_n_commits(min_commits):
            __log__.debug(
                'Download commits for package %s in repo %s.',
                package_name, repo.full_name)
            commits |= set(find_commits(github, repo, package_name))
        else:
            __log__.info(
                'Repository %s has less than %d commits. Skip.',
                repo.full_name, min_commits)
    return commits


def format_commit_info(item: Tuple[Repository, RepoCommit]) -> str:
    """Format commit information.

    :param Tuple[Repository, RepoCommit] item:
        Repository and commit to return info about.
    :returns str:
        Repository name, commit hash, and commit message.
    """
    repo, commit = item
    return {
        'Repository': repo.full_name,
        'Commit': commit.sha,
        'Message': commit.commit.message
        }


def print_commit_sample(
        outfile: IO[str], package_list: IO[str],
        min_commits: int, sample_size: int,
        github: RepoVerifier):
    """Print commit descriptions to stream.

    Take a sample of commits from repositories in package_list and print
    information about each commit to outfile.

    Only commits that change a path associated with package names in
    package_list are considered.

    :param IO[str] outfile:
        File to write output to.
    :param IO[str] package_list:
        Readable file match package names to repositories.
    :param int min_commits:
        Minimum number of commits in a repositoriy to be considered.
    :param int sample_size:
        Number of commits to randomly draw.
    :param RepoVerifier github:
        Instance to access Github API v3.
    """
    csv_writer = csv.DictWriter(outfile, fieldnames=OUTPUT_FIELDNAMES)
    commits = collect_commits(package_list, min_commits, github)
    if len(commits) > sample_size:
        sample = random.sample(commits, sample_size)
    else:
        sample = commits
    csv_writer.writeheader()
    csv_writer.writerows(sorted(map(format_commit_info, sample)))


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    __log__.info('------- Arguments: -------')
    __log__.info('Reading package_list from %s', args.package_list.name)
    __log__.info('Skipping repos with fewer than %d commits', args.min_commits)
    __log__.info('Sample size: %d', args.sample_size)
    __log__.info('Write output to %s', args.outfile.name)
    __log__.info('------- Arguments end -------')
    token = os.getenv('GITHUB_AUTH_TOKEN')
    print_commit_sample(
        args.outfile, args.package_list, args.min_commits,
        args.sample_size, RepoVerifier(token=token))
