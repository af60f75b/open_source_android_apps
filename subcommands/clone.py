"""Clone Github repositories listed in CSV file.

The CSV file needs to contain a column full_name that lists the identifier of
the Github repository in the format <ownwer-login>/<repo-name>.

Repositories can be filitered by a minimum number of commits requirement.

Use -h or --help for more information.
"""
import argparse
import csv
import logging
import os
import sys
from typing import IO
import git
from util.github_repo import RepoVerifier


__log__ = logging.getLogger(__name__)


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Add arguments to parser."""
    parser.add_argument(
        '-o', '--outdir', default='out/github_repos', type=str,
        help='Prefix to clone repositories into. Default: out/github_repos.')
    parser.add_argument(
        '-r', '--repo_list', default=sys.stdin,
        type=argparse.FileType('r'),
        help='''CSV file that contains repository names. The file needs
            to contain a column 'full_name'. Default: stdin.''')
    parser.add_argument(
        '-c', '--min_commits', default=2, type=int,
        help='''Minimum number of commits in main branch for repository
            to be cloned. CSV file needs to have column commit_count for
            this to work.''')
    parser.set_defaults(func=_main)


def clone_repo(full_name: str, outdir: str, github: RepoVerifier):
    """Clone repository from Github.

    :param str full_name:
        Full name of repository in format <owner-login>/<repo-name>.
    :param str outdir:
        Prefix to clone repository into.
    :param RepoVerifier github:
        Instance of Github API.
    """
    repo_info = github.get_repo(full_name)
    if not repo_info:
        __log__.warning('Cannot get repository %s from Github', full_name)
        return
    path = os.path.join(outdir, '{}.git'.format(full_name))
    __log__.info(
        'Clone branch %s of %s into %s', repo_info.default_branch,
        repo_info.clone_url, path)
    repo = git.Repo.clone_from(
        repo_info.clone_url, path, bare=True, branch=repo_info.default_branch)
    if repo:
        __log__.debug('Succesfully cloned into %s', repo.git_dir)
        repo.close()
    else:
        __log__.error('Failed cloning %s', repo_info.clone_url)


def clone_repositories(repo_list: IO[str], min_commits: int, outdir: str):
    """Clone repositories in CSV file repo_list from Github.

    :param IO[str] repo_list:
        Readable CSV file to read table from. Must contain column full_name.
    :param int min_commits:
        Minumum number of commits on main branch to be cloned. repo_list needs
        to have a field commit_count.
    :param str outdir:
        Prefix at which repositories are cloned.
        Paths for repositories are created at <outdir>/<full_name>
    """
    csv_reader = csv.DictReader(repo_list)
    github = RepoVerifier(token=os.getenv('GITHUB_AUTH_TOKEN'))
    if 'full_name' not in csv_reader.fieldnames:
        __log__.critical('Input is missing column `full_name`')
        sys.exit(1)
    if min_commits > 0 and 'commit_count' not in csv_reader.fieldnames:
        __log__.critical(
            'Cannot filter by commit count because input does not '
            'have a column `commit_count`')
        sys.exit(1)
    for row in csv_reader:
        if not min_commits or int(row['commit_count']) >= min_commits:
            clone_repo(row['full_name'], outdir, github)
        else:
            __log__.info(
                'Repository %s has %s commits. Required: %d', row['repo_name'],
                row['commit_count'], min_commits)


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    __log__.debug('Reading from %s', args.repo_list.name)
    clone_repositories(args.repo_list, args.min_commits, args.outdir)
