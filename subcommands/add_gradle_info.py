"""Add columns to CSV file: 'has_gradle_files', 'renamed_to', 'not_found'

In an earlier version find_gradle_files.py did not write any information to a
CSV file but only stored gradle files it found in a directory for each
repository.

This script parses the directories for all repositories and extends an input
CSV file with above mentioned columns.

Use -h or --help for more information.
"""
import argparse
import csv
import glob
import logging
import os
import sys
from typing import IO


__log__ = logging.getLogger(__name__)


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Define commandline arguments."""
    parser.add_argument(
        '--outdir', default='out/gradle_files', type=str,
        help='Directory to read gradle files from. Default: out/gradle_files.')
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


def has_gradle_files(repo_name: str, outdir: str) -> bool:
    """Test if any gradle files are stored for repo_name.

    Follows symlinks.

    :param str repo_name:
        Full name of repository.
    :param str outdir:
        Prefix to search for gradle files.
    :returns bool:
        True if any *.gradle files exist with prefix <outdir>/<repo_name>/
    """
    pattern = os.path.join(outdir, repo_name, '**/*.gradle')
    return len(glob.glob(pattern, recursive=True)) > 0


def get_new_repo_name(repo_name: str, outdir: str) -> str:
    """Find repository pointed to by symlink.

    :param str repo_name:
        Full name of repository.
    :param str outdir:
        Prefix to both name and target of symlinks.
    :returns str:
        two path components after outdir that <outdir>/<repo_name> links to, if
        that is a symlink. Empty string otherwise.
    """
    path = os.path.join(outdir, repo_name)
    if not os.path.lexists(path):
        return ''
    real_path = os.path.realpath(path)
    real_outdir = os.path.realpath(outdir)
    new_name = os.path.relpath(real_path, real_outdir)
    return new_name if new_name != repo_name else ''


def update_csv_table(repo_list: IO[str], outdir: str, output_list: IO[str]):
    """Update table read from repo_list with data from outdir.

    For each row in repo_list, read field full_name, look for a path in outdir.
     - If the path is a symlink: Fill field renamed_to with name of link
       target. Otherwise enter the empty string to the field.
     - If the path is a directory and contains gradle files, fill field
       has_gradle_files with True, otherwise with False.

    Information if repository does not exist anymore cannot be recovered from
    outdir contents. Leave the field empty.

    Write extended table to output_list.

    :param IO[str] repo_list:
        Readable CSV file to read table from. Must contain column full_name.
    :param str outdir:
        Prefix at which directories and symlinks for repositories are stored.
        Paths for repositories are expected at <outdir>/<full_name>
    :param IO[str] output_list:
        Writable file to write extended table to.
    """
    csv_reader = csv.DictReader(repo_list)
    fieldnames = csv_reader.fieldnames + [
        'has_gradle_files', 'renamed_to', 'not_found']
    csv_writer = csv.DictWriter(output_list, fieldnames)
    csv_writer.writeheader()
    for row in csv_reader:
        repo_name = row['full_name']
        row.update({
            'has_gradle_files': has_gradle_files(repo_name, outdir),
            'renamed_to': get_new_repo_name(repo_name, outdir),
            'not_found': '',
            })
        csv_writer.writerow(row)


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    __log__.debug('Reading from %s', args.repo_list.name)
    update_csv_table(args.repo_list, args.outdir, args.output_list)
