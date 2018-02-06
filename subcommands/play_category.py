"""Scrape Google Play category data from Google Play."""

import argparse
import json
import logging
import os

from lxml.html import html5parser
import requests

from util.parse import parse_package_details


__log__ = logging.getLogger(__name__)


PLAY_STORE_LINK = 'https://play.google.com/store/apps/details?id={}'
CATEGORY_DIR = 'categories'
HEADERS = {
    'Accept-Language': 'en,en-GB;q=0.8,en-US;q=0.7,de;q=0.5,de-DE;q=0.3,nl;q=0.2'
    }


def get_play_page(package_name):
    url = PLAY_STORE_LINK.format(package_name)
    __log__.info('Request %s', url)
    return requests.get(url, headers=HEADERS)


def find_category_string(html_text):
    parser = html5parser.fromstring(html_text)
    try:
        category_link = parser.cssselect('.category')[0]
        category_span = category_link.cssselect('[itemprop=genre]')[0]
        return category_span.text
    except IndexError as e:
        __log__.exception('Cannot match category in HTML')
        return None


def write_category_file(package_name, category, details_dir):
    category_path = os.path.join(details_dir, CATEGORY_DIR)
    os.makedirs(category_path, exist_ok=True)
    file_name = '{}.json'.format(package_name)
    file_path = os.path.join(category_path, file_name)
    with open(file_path, 'w') as json_file:
        json.dump({
            'packageName': package_name,
            'appCategory': category
            }, json_file)
    __log__.info('Wrote %s', file_path)


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Add arguments to parser."""
    parser.add_argument(
        'PLAY_STORE_DETAILS_DIR', type=str,
        help='Directory containing JSON files with details from Google Play.')
    parser.set_defaults(func=_main)


def _main(args):
    """Pass arguments to respective function."""
    __log__.info('------- Arguments: -------')
    __log__.info('PLAY_STORE_DETAILS_DIR: %s', args.PLAY_STORE_DETAILS_DIR)

    for package_name, _ in parse_package_details(args.PLAY_STORE_DETAILS_DIR):
        response = get_play_page(package_name)
        category = find_category_string(response.text)
        if not category:
            continue
        __log__.info('Found category "%s" for %s', category, package_name)
        write_category_file(package_name, category, args.PLAY_STORE_DETAILS_DIR)
