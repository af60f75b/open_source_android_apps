"""Filter out package names not available in Google Play.

For each package name in input, check if package name is available in
Google Play. If so, print package name to output.

Input and output have each package name on a separate lines.

Use -h or --help for more information.
"""

import argparse
import logging
import sys
from typing import IO
import requests


__logger__ = logging.getLogger(__name__)


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Define commandline arguments."""
    parser.add_argument(
        '--input', default=sys.stdin,
        type=argparse.FileType('r'),
        help='File to read package names from. Default: stdin.')
    parser.add_argument(
        '--output', default=sys.stdout,
        type=argparse.FileType('w'),
        help='Output file. Default: stdout.')
    parser.add_argument(
        '--log', default=sys.stderr,
        type=argparse.FileType('w'),
        help='Log file. Default: stderr.')
    parser.add_argument(
        '--include-403', action='store_true',
        help='''Include package names which Google Play returns
            status `403 Unauthorized` for.''')
    parser.set_defaults(func=_main)


def is_package_in_play(package_name: str, include_403: bool) -> bool:
    """Test if package_name is available in Google Play.

    Response code `200 Success` is considered an indicator of
    availability. So is response code `403 Unauthorized` in case
    include_403 is True.

    :param str package_name: Package name to search for in Google Play.
    :param bool include_403: Consider packages valid that get a
        response code `403 Unauthorized`.
    :returns bool: True if package name is available in Google Play,
        False otherwise.
    """
    response = requests.head(
            'https://play.google.com/store/apps/details',
            params={ 'id': package_name })

    log_msg = 'Status {} for {}'.format(
            response.status_code, response.url)
    if response.status_code != 200 and response.status_code != 404:
        __logger__.error(log_msg)
    else:
        __logger__.info(log_msg)

    return response.status_code == 200 or (include_403 and
            response.status_code == 403)


def package_filter(input_file: IO[str], output_file: IO[str],
        include_403=False):
    """Filter out lines if they do not exist in Google Play.

    :param IO[str] input_file: File to read lines from. Each line is
        considered a package name to test.
    :param IO[str] output_file: File to write package names to if they
        pass the filter.
    """
    for line in input_file.readlines():
        package = line.strip()
        if is_package_in_play(package, include_403):
            print(package, file=output_file)


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    __logger__.debug('Reading from %s', args.input.name)
    package_filter(args.input, args.output, args.include_unauthorized)
