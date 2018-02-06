"""Download package meta data from Google Play.

For each package name in input, use node-google-play-cli to fetch meta
data from Google Play and store resulting JSON in out directory.

Input expects each package name on a separate line.

Output JSON files are stored in <outdir>/<package_name>.json. Out
directory will be created if it does not exist and individual files
will be overwritten if they exist.

Executable bulk-details from node-google-play-cli is used to communicate
with Google Play (https://github.com/dweinstein/node-google-play-cli).
"""

import argparse
import itertools
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, IO, Iterable, Iterator, List, Mapping, TypeVar


NODE_GOOGLE_PLAY_CLI_BULK_BIN = '/usr/bin/gp-bulk-details'
# Manual testing indicates a limit of 1k. Leave a margin
BULK_SIZE = 900
DELAY = 12 # in seconds

logger = logging.getLogger(__name__)


T = TypeVar('T')


def grouper(items: Iterable[T], n: int) -> Iterator[List[T]]:
    """Group items into n sized groups.

    :param Iterable[T] items: Iterator to take elements from.
    :param int n: Group size.
    :returns Iterator[List[T]]: Iterator of lists of length n. Last list
        might be shorter than n.
    """
    it = iter(items)
    while True:
        group = list(itertools.islice(it, n))
        if not group:
            return
        yield group


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Define commandline arguments."""
    parser.add_argument('--input', default=sys.stdin,
            type=argparse.FileType('r'),
            help='File to read package names from. Default: stdin.')
    parser.add_argument('--outdir', default='out/', type=str,
            help='Out directory. Default: out/.')
    parser.add_argument('--bulk_details-bin',
            default=NODE_GOOGLE_PLAY_CLI_BULK_BIN, type=str,
            help='Path to node-google-play-cli bulk-details binary. '
            'Default: {}'.format(NODE_GOOGLE_PLAY_CLI_BULK_BIN))
    parser.set_defaults(func=_main)


def bulk_fetch_details(package_names: List[str]) -> Mapping[str, Any]:
    """Download meta data for all package names from Google Play.

    :param List[str] package_names: Package names to download meta data
        for.
    :returns Mapping[str, Any]: Dictionary with package names mapped to
        meta data. Meta data is either a dictionary or None if the
        package is not accessible.
    """
    if not package_names:
        return {}

    try:
        process = subprocess.run(
                [NODE_GOOGLE_PLAY_CLI_BULK_BIN] + package_names,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=True, universal_newlines=True)
        return dict(zip(package_names, json.loads(process.stdout)))
    except subprocess.CalledProcessError as e:
        logger.warn('%s', e)
        logger.debug(process.stderr)
        logger.debug('First package: %s; last package: %s',
                package_names[0], package_names[-1])
        return {}


def download_package_details(input_file: IO[str], out_dir: str):
    """Download meta data for each package name from Google Play.

    Stores one JSON files for each package in out_dir.

    :param IO[str] input_file: File to read lines from. Each line is
        considered a package name to test.
    :param str out_dir: Directory name to store JSON files in.
    """
    os.makedirs(out_dir, exist_ok=True)

    package_iterator = map(lambda l: l.strip(), input_file)
    for packages in grouper(package_iterator, BULK_SIZE):
        for package, meta_data in bulk_fetch_details(packages).items():
            filename = '{}.json'.format(package)
            path = os.path.join(out_dir, filename)
            with open(path, 'w') as output_file:
                json.dump(meta_data, output_file, indent=2)
        time.sleep(DELAY)


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    global NODE_GOOGLE_PLAY_CLI_BULK_BIN
    NODE_GOOGLE_PLAY_CLI_BULK_BIN = args.bulk_details_bin
    logger.debug('Reading from %s', args.input.name)
    download_package_details(args.input, args.outdir)
