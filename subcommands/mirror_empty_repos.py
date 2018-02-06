"""Some repositories are empty after the mirroring script.

Fix this by mirroring the repos again.
"""

import argparse
import csv
import logging
import re
import sys
import time

from gitlab import Gitlab
from gitlab.exceptions import GitlabGetError

from util.parse import get_latest_repo_name


__log__ = logging.getLogger(__name__)


GITLAB_HOST = 'http://145.108.225.21'
GITLAB_TOKEN_FILE = '.gitlab.private_token'
OLD_REPOSITORY_DATA = 'input/github_repo_data.new.complete.utf8.csv'
EMPTY_REPOSITORY_LIST = 'output/all-empty-repos-no-wikis.txt'


class GithubToGitlabName(object):
    """Converter for repository names from GitHub to Gitlab"""
    def __getitem__(self, character):
        if (ord('_') == character
                or ord('a') <= character <= ord('z')
                or ord('0') <= character <= ord('9')):
            return character
        if ord('A') <= character <= ord('Z'):
            return character + (ord('a') - ord('A'))
        if ord('/') == character:
            return ord('_')
        return ord('-')

    @staticmethod
    def convert(repo_name):
        """Convert GitHub name to estimated Gitlab name."""
        step1 = repo_name.translate(GithubToGitlabName())
        step2 = re.sub(r'-+', '-', step1)
        return re.sub(r'-+$', '', step2)


def _gitlab_instance():
    with open(GITLAB_TOKEN_FILE) as token_file:
        token = token_file.readline().strip()
    return Gitlab(GITLAB_HOST, private_token=token, api_version=4)


def _load_repository_data():
    with open(OLD_REPOSITORY_DATA) as csv_file:
        result = list(csv.DictReader(csv_file))
        __log__.info('Loaded repo data with %d entries', len(result))
        return result


def _read_empty_repos():
    with open(EMPTY_REPOSITORY_LIST) as input_file:
        result = list(map(str.strip, input_file.readlines()))
        __log__.info('Loaded list with %d empty repos', len(result))
        return result


def _by_gitlab_name():
    result = {}
    for row in _load_repository_data():
        original, latest = get_latest_repo_name(row)
        # FIXME: Gitlab repo could be found more reliably with
        #        row['clone_repo_id']
        #        The current approach has the advantage, that it runs
        #        locally.
        key = GithubToGitlabName.convert(row['full_name'])
        names = result.setdefault(key, set())
        names.add(original)
        names.add(latest)
    __log__.info('Read all repositories')
    return result


def _find_github_name(gitlab_repo_name, repos):
    github_repos = repos.get(gitlab_repo_name, set())
    if len(github_repos) < 1:
        __log__.warning('Cannot find any repos for %s', gitlab_repo_name)
        return None
    elif len(github_repos) > 1:
        __log__.warning('Too many repos for %s', gitlab_repo_name)
        return None
    return list(github_repos)[0]


def _delete_repo(gitlab_repo_name, gitlab):
    try:
        gitlab_repo = gitlab.projects.get(
            'gitlab/{}'.format(gitlab_repo_name))
        __log__.info('Delete repo %s (%d)', gitlab_repo.name, gitlab_repo.id)
        gitlab_repo.delete()
    except GitlabGetError:
        __log__.warning('Project %s does not exist.', gitlab_repo_name)


def _import_from_github_to_gitlab(github_repo_name, gitlab_repo_name, gitlab):
    github_url = 'https://github.com/{}.git'.format(github_repo_name)
    new_repo = gitlab.projects.create({
        'name': gitlab_repo_name,
        'public': True,
        'import_url': github_url,
        })
    __log__.info('Created new repo: %s (%d)', new_repo.name, new_repo.id)
    return new_repo


def _log_args(args):
    """Pass arguments to respective function."""
    __log__.info('------- Constants: -------')
    __log__.info('GITLAB_HOST: %s', GITLAB_HOST)
    __log__.info('GITLAB_TOKEN_FILE: %s', GITLAB_TOKEN_FILE)
    __log__.info('OLD_REPOSITORY_DATA: %s', OLD_REPOSITORY_DATA)
    __log__.info('EMPTY_REPOSITORY_LIST: %s', EMPTY_REPOSITORY_LIST)
    __log__.info('------- Arguments: -------')
    __log__.info('--output: %s', args.output.name)
    __log__.info('------- Arguments end -------')


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Add arguments to parser."""
    parser.add_argument(
        '-o', '--output', type=argparse.FileType('w'), default=sys.stdout,
        help='File to write output to. Default: stdout.')
    parser.set_defaults(func=_main)


def _main(args):
    _log_args(args)

    repos = _by_gitlab_name()
    gitlab = _gitlab_instance()

    csv_writer = csv.DictWriter(args.output, [
        'github_full_name',
        'clone_project_name',
        'clone_project_path',
        'clone_project_id'
        ])
    csv_writer.writeheader()

    empty_repos = _read_empty_repos()
    repo_names = list()

    for gitlab_repo_name in empty_repos:
        github_repo_name = _find_github_name(gitlab_repo_name, repos)
        if not github_repo_name:
            continue
        repo_names.append((github_repo_name, gitlab_repo_name))

        _delete_repo(gitlab_repo_name, gitlab)

    __log__.info('Wait for 5 seconds for Gitlab to delete repos')
    time.sleep(5)
    __log__.info('Finished waiting: Continue')

    for github_repo_name, gitlab_repo_name in repo_names:
        gitlab_repo = _import_from_github_to_gitlab(
            github_repo_name, gitlab_repo_name, gitlab)

        csv_writer.writerow({
            'github_full_name': github_repo_name,
            'clone_project_name': gitlab_repo.name,
            'clone_project_path': gitlab_repo.path,
            'clone_project_id': gitlab_repo.id
            })
