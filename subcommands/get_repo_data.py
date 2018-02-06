"""Download information about repositories from Github.

Read CSV file as input and write information to output CSV file.

Use -h or --help for more information.
"""
import argparse
import csv
import logging
import os
import sys
from util.github_repo import RepoVerifier


__log__ = logging.getLogger(__name__)


CSV_COLUMNS = [
    'id', 'name', 'full_name', 'description', 'size', 'private', 'fork',
    'archived', 'created_at', 'updated_at', 'pushed_at', 'language',
    'default_branch', 'homepage', 'forks_count', 'stargazers_count',
    'subscribers_count', 'watchers_count', 'network_count', 'has_downloads',
    'has_issues', 'has_pages', 'has_projects', 'has_wiki', 'owner_id',
    'owner_login', 'owner_type', 'parent_id', 'source_id', 'commit_count'
    ]


def download_repo_data(full_name: str, github: RepoVerifier) -> dict:
    """Download data about repository.

    :param str full_name:
        Identifier of Github repository in format <repo-owner>/<repo-name>.
    :param RepoVerifier github:
        Github API wrapper to access Github data.
    :returns dict:
        Mapping of meta data names to values.
    """
    repo = github.get_repo(full_name)
    if repo:
        data = repo.meta_data
        data['commit_count'] = repo.count_commits()
        return data
    __log__.warning('Cannot get repository %s', full_name)
    return None


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Define commandline arguments."""
    parser.add_argument(
        '-o', '--out', default=sys.stdout,
        type=argparse.FileType('w'),
        help='CSV file to write meta data to.')
    parser.add_argument(
        '-p', '--package_list',
        default=sys.stdin,
        type=argparse.FileType('r'),
        help='''CSV file that matches package names to a repository.
            The file needs to contain a column for the package name and
            a second column with the repo name. Default: stdin.''')
    parser.set_defaults(func=_main)


def _main(args: argparse.Namespace):
    """Download info for repos in input to CSV file.

    :param argparse.Namespace args:
        Command line arguments.
    """
    __log__.debug('Reading from %s', args.package_list.name)
    repo_verifier = RepoVerifier(token=os.getenv('GITHUB_AUTH_TOKEN'))
    csv_reader = csv.reader(args.package_list)
    csv_writer = csv.DictWriter(args.out, CSV_COLUMNS)
    csv_writer.writeheader()
    for row in csv_reader:
        if len(row) > 1:
            repo_name = row[1]
            __log__.info('Get data for %s', repo_name)
            data = download_repo_data(repo_name, repo_verifier)
            if data:
                csv_writer.writerow(data)
        else:
            __log__.warning(
                'Package %s does not contain a repo name.', row[0])
