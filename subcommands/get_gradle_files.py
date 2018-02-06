"""Download gradle files from repositories on Github.
Read CSV file as input and write all files to outdir. Additional output is a
CSV file with columns has_gradle_files, renamed_to, and not_found added to
content of input file.

Use -h or --help for more information.
"""
import argparse
import csv
import logging
import os
import sys
from typing import Iterator
from github3.models import GitHubError
from github3.repos.contents import Contents
from github3.search import CodeSearchResult
from util.github_repo import RepoVerifier


__log__ = logging.getLogger(__name__)


class GradleFileSearcher(RepoVerifier):
    """Wrapper for Github API to download gradle files."""

    def search_gradle_files(self, repo: str) -> Iterator[CodeSearchResult]:
        """Search for gradle files in repository.

        This search term includes all files with either of build.gradle or
        settings.gradle anywhere in the path. Thus also unrelated files as
        foo/bar/settings.gradle/example.txt

        :param str repo:
            Full name of repository.
        :returns Iterator[CodeSearchResult]:
            Iterator over search results.
        """
        return self.search_code(
            'repo:{} in:path build.gradle OR settings.gradle'.format(repo))

    def iter_gradle_files(self, repo_name: str) -> Iterator[Contents]:
        """Iterate over gradle files in repostitory.

        :param str full_name:
            Identifier of Github repository in format <repo-owner>/<repo-name>.
        :returns Iterator[Contents]:
            Iterator over gradle files in repository.
        """
        for result in self.search_gradle_files(repo_name):
            # Filter out files that are not gradle files but have gradle in
            # their prefix
            if result.path.endswith('.gradle'):
                yield result.repository.contents(result.path)


def makedirs(path: str):
    """Recursively create directories.

    :param str path:
        Full path including filename. Basename will be stripped unless it
        ends in /.
    """
    dirname = os.path.dirname(path)
    os.makedirs(dirname, exist_ok=True)


def download_gradle_files(
        repo_name: str, github: GradleFileSearcher, outdir: str) -> bool:
    """Download gradle files from repository.

    All files will end up in subdirectories of the following template:
    <outdir>/<repo_name>/<path_in_repo>/build.gradle

    :param str repo_name:
        Identifier of Github repository in format <repo-owner>/<repo-name>.
    :param GradleFileSearcher github:
        Github API wrapper to download gradle files.
    :param str outdir:
        Name of directory to download files to.
    :returns bool:
        True if repository contains at least one gradle file, otherwise False.
    """
    has_gradle_files = False
    for gradle_file in github.iter_gradle_files(repo_name):
        has_gradle_files = True
        path = os.path.join(outdir, repo_name, gradle_file.path)
        makedirs(path)
        with open(path, 'wb') as output_file:
            # Ensure input to write() is of type bytes even if emtpy
            output_file.write(gradle_file.decoded or b'')
    return has_gradle_files


def symlink_repo(outdir: str, old_name: str, new_name: str):
    """Create a symlink from outdir/old_name to outdir/new_name.

    May create dead links if outdir/new_name does not exist.

    :param str outdir:
        Prefix for both link and target.
    :param str old_name:
        Name of symlink to create.
    :param str new_name:
        Name of target to symlink to.
    """
    old_path = os.path.join(outdir, old_name)
    dirname, basename = os.path.split(old_path)
    if not basename:
        old_path = dirname
        dirname, basename = os.path.split(old_path)
    print(dirname, basename)
    makedirs(os.path.join(dirname, ''))  # End in / to make full path

    new_path = os.path.join(outdir, new_name, '')
    rel_path = os.path.relpath(new_path, dirname)
    os.symlink(rel_path, old_path)


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Define commandline arguments."""
    parser.add_argument(
        '--outdir', default='out/gradle_files', type=str,
        help='Directory to safe gradle files to. Default: out/gradle_files.')
    parser.add_argument(
        '-r', '--repo_list',
        default=sys.stdin,
        type=argparse.FileType('r'),
        help='''CSV file that contains repository names. The file needs
            to contain a column 'full_name'. Default: stdin.''')
    parser.add_argument(
        '--output_list', default=sys.stdout,
        type=argparse.FileType('w'),
        help='''CSV file to write updated repository information to. This file
            will contain the same information as REPO_LIST extended with three
            columns: has_gradle_files, renamed_to, and not_found. These columns
            indicate if the repository contains at least one gradle
            configuration file, the name the repository has been renamed to,
            and if the repository has not been found anymore, respectively.''')
    parser.set_defaults(func=_main)


def _main(args: argparse.Namespace):
    """Download info for repos in input to CSV file.

    :param argparse.Namespace args:
        Command line arguments.
    """
    def _download_gradle_files(repo_name: str) -> bool:
        """Closure for download_gradle_files."""
        __log__.info('Get gradle files in %s', repo_name)
        return download_gradle_files(repo_name, github, args.outdir)

    __log__.debug('Reading from %s', args.repo_list.name)
    github = GradleFileSearcher(token=os.getenv('GITHUB_AUTH_TOKEN'))
    csv_reader = csv.DictReader(args.repo_list)
    fieldnames = csv_reader.fieldnames + [
        'has_gradle_files', 'renamed_to', 'not_found']
    csv_writer = csv.DictWriter(args.output_list, fieldnames)
    csv_writer.writeheader()
    for row in csv_reader:
        repo_name = row['full_name']
        row.update({
            'has_gradle_files': False,
            'renamed_to': '',
            'not_found': False,
            })
        new_name, has_gradle_files = github.catch_renamed_repo(repo_name)
        if new_name:
            row['has_gradle_files'] = has_gradle_files
            if new_name != repo_name:
                row['renamed_to'] = new_name
                symlink_repo(args.outdir, repo_name, new_name)
        else:
            row['not_found'] = True
        csv_writer.writerow(row)
