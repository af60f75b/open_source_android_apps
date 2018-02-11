"""Create CSV files used for Neo4j import."""
import argparse
import csv
import logging
import os
import sys
from typing import Iterator

from util.parse import parse_google_play_info, parse_iso8601


# Some commit messages in the dataset are excessively long
csv.field_size_limit(sys.maxsize)


__log__ = logging.getLogger(__name__)


REPOSITORY_FIELDS = [
    ':LABEL',
    'id:ID',
    'owner:string',
    'name:string',
    'snapshot:string',
    'snapshotTimestamp:long',
    'description:string',
    'createdAt:long',
    'forksCount:int',
    'stargazersCount:int',
    'subscribersCount:int',
    'watchersCount:int',
    'networkCount:int',
    'ownerType:string',
    'parentId:long',
    'sourceId:long',
]

PLAY_PAGE_FIELDS = [
    ':LABEL',
    ':ID',
    'docId:string',
    'uri:string',
    'snapshotTimestamp:long',
    'title:string',
    'appCategory:string[]',
    'promotionalDescription:string',
    'descriptionHtml:string',
    'translatedDescriptionHtml:string',
    'versionCode:int',
    'versionString:string',
    'uploadDate:long',
    'formattedAmount:string',
    'currencyCode:string',
    'in-app purchases:string',
    'installNotes:string',
    'starRating:float',
    'numDownloads:string',
    'developerName:string',
    'developerEmail:string',
    'developerWebsite:string',
    'targetSdkVersion:int',
    'permissions:string[]',
]

COMMIT_FIELDS = [
    ':LABEL',
    'id:ID',
    'short_id:string',
    'title:string',
    'message:string',
    'additions:int',
    'deletions:int',
    'total:int',
]

APP_FIELDS = [
    ':LABEL',
    'id:ID',
]

BRANCH_FIELDS = [
    ':LABEL',
    ':ID',
    'name:string',
]

TAG_FIELDS = [
    ':LABEL',
    ':ID',
    'name:string',
    'message:string',
]

CONTRIBUTOR_FIELDS = [
    ':LABEL',
    ':ID',
    'email:string',
    'name:string',
]

GENERAL_RELATION_FIELDS = [
    ':TYPE',
    ':START_ID',
    ':END_ID',
]

CONTRIBUTOR_RELATION_FIELDS = GENERAL_RELATION_FIELDS + ['timestamp:long']
IMPLEMENTED_RELATION_FIELDS = GENERAL_RELATION_FIELDS + [
    'manifestPaths:string[]',
    'gradleConfigPaths:string[]',
    'mavenConfigPaths:string[]',
]

CONTRIBUTOR_TYPE_AUTHOR = 'AUTHOR'
CONTRIBUTOR_TYPE_COMMITTER = 'COMMITTER'

COMMITS_RELATION = 'COMMITS'
AUTHORS_RELATION = 'AUTHORS'
BELONGS_TO_RELATION = 'BELONGS_TO'
POINTS_TO_RELATION = 'POINTS_TO'
IMPLEMENTED_BY_RELATION = 'IMPLEMENTED_BY'
PUBLISHED_AT_RELATION = 'PUBLISHED_AT'
PARENT_RELATION = 'PARENT'


def node_index(prefix: str, domain_id: str = None) -> str:
    """Provide unique identifiers for nodes."""
    if domain_id:
        return '{}:{}'.format(prefix, domain_id)

    # Create a member of node_index to keep counter between calls
    try:
        node_index.counter += 1
    except AttributeError:
        node_index.counter = 1

    return '{}:{}'.format(prefix, node_index.counter)


def format_relation(
        relation_type: str, start_id: str, end_id: str, **properties) -> dict:
    """Formats a relation."""
    relation = {
        ':TYPE': relation_type,
        ':START_ID': start_id,
        ':END_ID': end_id,
    }
    relation.update(properties)
    return relation


def format_belongs_to(start_id: str, end_id: str) -> dict:
    """Format a :BELONGS_TO relation."""
    return format_relation(BELONGS_TO_RELATION, start_id, end_id)


def format_points_to(start_id: str, end_id: str) -> dict:
    """Format a :POINTS_TO relation."""
    return format_relation(POINTS_TO_RELATION, start_id, end_id)


def format_parent(start_id: str, end_id: str) -> dict:
    """Format a :PARENT relation."""
    return format_relation(PARENT_RELATION, start_id, end_id)


def format_implemented(input_row: dict, repo_id: str) -> dict:
    """Format data for :IMPLEMENTED_BY relation for Neo4j import."""
    return format_relation(
        IMPLEMENTED_BY_RELATION, input_row['package'], repo_id,
        **{
            'manifestPaths:string[]':
                input_row['manifestPaths'].replace(',', ';'),
            'gradleConfigPaths:string[]':
                input_row['gradleConfigPaths'].replace(',', ';'),
            'mavenConfigPaths:string[]':
                input_row['mavenConfigPaths'].replace(',', ';'),
        })


def format_contributor(input_row: dict, contributor_type: str) -> tuple:
    """Extract data for Neo4j import from input_row."""
    if contributor_type == CONTRIBUTOR_TYPE_COMMITTER:
        email_key = 'author_email'
        name_key = 'author_name'
        time_key = 'authored_date'
        relation_type = COMMITS_RELATION
    elif contributor_type == CONTRIBUTOR_TYPE_AUTHOR:
        email_key = 'committer_email'
        name_key = 'committer_name'
        time_key = 'committed_date'
        relation_type = AUTHORS_RELATION
    else:
        raise ValueError('Unknown contributor_type: {}'.format(
            contributor_type))

    email = input_row[email_key].strip()
    node_id = node_index('contr', email)
    node = {
        ':LABEL': 'Contributor',
        ':ID': node_id,
        'email:string': email,
        'name:string': input_row[name_key],
    }
    relation = format_relation(
        relation_type, node_id, input_row['id'],
        **{'timestamp:long': input_row[time_key]})
    return node_id, node, relation


def format_author(input_row: dict) -> tuple:
    """Format a author row form commit input_row."""
    return format_contributor(input_row, CONTRIBUTOR_TYPE_AUTHOR)


def format_committer(input_row: dict) -> tuple:
    """Format a committer row form commit input_row."""
    return format_contributor(input_row, CONTRIBUTOR_TYPE_COMMITTER)


def format_tag(input_row: dict, repo_id: str) -> tuple:
    """Convert input_row for Neo4j import."""
    node_id = node_index('tag')
    node = {
        ':LABEL': 'Tag',
        ':ID': node_id,
        'name:string': input_row['tag_name'],
        'message:string': escape(input_row['tag_message']),
    }
    belongs_relation = format_belongs_to(node_id, repo_id)
    points_relation = format_points_to(node_id, input_row['commit_hash'])
    return node, belongs_relation, points_relation


def format_branch(input_row: dict, repo_id: str) -> tuple:
    """Convert input_row for Neo4j import."""
    node_id = node_index('branch')
    node = {
        ':LABEL': 'Branch',
        ':ID': node_id,
        'name:string': input_row['branch_name'],
    }
    belongs_relation = format_belongs_to(node_id, repo_id)
    points_relation = format_points_to(node_id, input_row['commit_hash'])
    return node, belongs_relation, points_relation


def format_app(package_name: str) -> dict:
    """Format CSV row for package name."""
    return {
        ':LABEL': 'App',
        'id:ID': package_name,
    }


def format_commit(input_row: dict, repo_id: str) -> dict:
    """Convert input_row for import to Neo4j."""
    node_id = input_row['id']
    node = {
        ':LABEL': 'Commit',
        'id:ID': node_id,
        'short_id:string': input_row['short_id'],
        'title:string': input_row['title'],
        'message:string': escape(input_row['message']),
        'additions:int': input_row['additions'],
        'deletions:int': input_row['deletions'],
        'total:int': input_row['total'],
    }
    belongs_relation = format_belongs_to(node_id, repo_id)
    author_id, author_node, author_relation = format_author(input_row)
    committer_id, committer_node, committer_relation = format_committer(
        input_row)
    contributors = {
        author_id: author_node,
        committer_id: committer_node,
    }
    parent_relations = [
        format_parent(node_id, parent_id)
        for parent_id in input_row['parent_ids'].split(',')
        if parent_id
    ]
    return {
        'commit': node,
        'authors': author_relation,
        'commits': committer_relation,
        'belongs': belongs_relation,
        'contributors': contributors,
        'parents': parent_relations
    }


def format_play_page(package_name: str, input_dir: str, mtime: int) -> tuple:
    """Read data for GooglePlayPage in right format."""
    details_dir = os.path.join(input_dir, 'package_details')
    node_id = node_index('play')
    data = parse_google_play_info(package_name, details_dir)
    if not data:
        data = {}
    node = {
        ':LABEL': 'GooglePlayPage',
        ':ID': node_id,
        'docId:string': package_name,
        'uri:string': data.get('uri'),
        'snapshotTimestamp:long': mtime,
        'title:string': data.get('title'),
        'appCategory:string[]': ';'.join(data.get('appCategory') or []),
        'promotionalDescription:string':
            escape(data.get('promotionalDescription')),
        'descriptionHtml:string': escape(data.get('descriptionHtml')),
        'translatedDescriptionHtml:string':
            escape(data.get('translatedDescriptionHtml')),
        'versionCode:int': data.get('versionCode'),
        'versionString:string': data.get('versionString'),
        'uploadDate:long': data.get('uploadDate'),
        'formattedAmount:string': data.get('formattedAmount'),
        'currencyCode:string': data.get('currencyCode'),
        'in-app purchases:string': data.get('in-app purchases'),
        'installNotes:string': data.get('installNotes'),
        'starRating:float': data.get('starRating'),
        'numDownloads:string': data.get('numDownloads'),
        'developerName:string': data.get('developerName'),
        'developerEmail:string': data.get('developerEmail'),
        'developerWebsite:string': data.get('developerWebsite'),
        'targetSdkVersion:int': data.get('targetSdkVersion'),
        'permissions:string[]': ';'.join(data.get('permissions') or []),
    }
    relation = format_relation(PUBLISHED_AT_RELATION, package_name, node_id)
    return node, relation


def format_repository(input_row: dict, snapshot: dict) -> dict:
    """Formats input_row for Neo4j import."""
    if snapshot.get('created_at'):
        timestamp = parse_iso8601(snapshot.get('created_at'))
    else:
        timestamp = ''
    node_id = input_row['id']
    return {
        ':LABEL': 'GitHubRepository',
        'id:ID': node_id,
        'owner:string': input_row['owner_login'],
        'name:string': input_row['name'],
        'snapshot:string': snapshot.get('web_url'),
        'snapshotTimestamp:long': timestamp,
        'description:string': escape(input_row['description']),
        'createdAt:long': parse_iso8601(input_row['created_at']),
        'forksCount:int': input_row['forks_count'],
        'stargazersCount:int': input_row['stargazers_count'],
        'subscribersCount:int': input_row['subscribers_count'],
        'watchersCount:int': input_row['watchers_count'],
        'networkCount:int': input_row['network_count'],
        'ownerType:string': input_row['owner_type'],
        'parentId:long': input_row['parent_id'],
        'sourceId:long': input_row['source_id']
    }


def get_repository_csv_path(repo_id: str, input_dir: str, name: str) -> str:
    """Get directory where CSV files of a repository are."""
    return os.path.join(
        input_dir, 'repository_details', repo_id, name)


def read_snapshot(repo_id: str, input_dir: str) -> dict:
    """Read Gitlab snapshot data from CSV file."""
    path = get_repository_csv_path(repo_id, input_dir, 'snapshot.csv')
    with open(path) as csv_file:
        for row in csv.DictReader(csv_file):
            # We are only interested in the first (and only) entry.
            return row
    return {}


def iter_implemented_rel(repo_id: str, input_dir: str) -> Iterator[dict]:
    """Read :IMPLEMENTED_BY relation properties."""
    path = get_repository_csv_path(repo_id, input_dir, 'paths.csv')
    with open(path) as csv_file:
        for row in csv.DictReader(csv_file):
            yield format_implemented(row, repo_id)


def iter_commit_rows(repo_id: str, input_dir: str) -> Iterator[tuple]:
    """Open commit CSV file for repo_id and format rows."""
    path = get_repository_csv_path(repo_id, input_dir, 'commits.csv')
    with open(path) as csv_file:
        try:
            for row in csv.DictReader(csv_file):
                yield format_commit(row, repo_id)
        except csv.Error as error:
            __log__.exception('Repo ID: %d.', repo_id)
            raise error


def iter_repository_rows(input_dir: str) -> Iterator[tuple]:
    """Converts all rows in input_file to Neo4j import format."""
    path = os.path.join(input_dir, 'repositories.csv')
    with open(path) as input_file:
        for row in csv.DictReader(input_file):
            repo_id = row['id']
            yield (
                repo_id,
                format_repository(row, read_snapshot(repo_id, input_dir)),
                row['packages'].split(',')
            )


def iter_tag_rows(repo_id: str, input_dir: str) -> Iterator[tuple]:
    """Iterate over tag rows of a repository."""
    path = get_repository_csv_path(repo_id, input_dir, 'tags.csv')
    with open(path) as input_file:
        for row in csv.DictReader(input_file):
            yield format_tag(row, repo_id)


def iter_branch_rows(repo_id: str, input_dir: str) -> Iterator[tuple]:
    """Iterate over branch rows of a repository."""
    path = get_repository_csv_path(repo_id, input_dir, 'branches.csv')
    with open(path) as input_file:
        for row in csv.DictReader(input_file):
            yield format_branch(row, repo_id)


def read_package_snapshot_times(input_dir: str) -> dict:
    """Read CSV file with snapshot times of packages."""
    path = os.path.join(input_dir, 'play_snapshots.csv')
    with open(path) as input_file:
        return {row[0]: row[1] for row in csv.reader(input_file)}


def add_rel_to_set(rel: dict, rel_set: set):
    """Add a relation to a set.

    Use tuple of :TYPE, :START_ID, and :END_ID as index.
    """
    key = rel[':TYPE'], rel[':START_ID'], rel[':END_ID']
    rel_set[key] = rel


def prepare_for_neo4j_import(input_dir: str, output_dir: str):
    """Convert all rows in input_file to Neo4j import."""
    contributors = {}
    commits = {}
    general_relations = {}
    contribute_relations = {}
    mtimes = read_package_snapshot_times(input_dir)
    with Output(output_dir) as output:
        for repo_id, repo, packages in iter_repository_rows(input_dir):
            output.repo(repo)
            for commit in iter_commit_rows(repo_id, input_dir):
                # There are duplicate commit entries. Probably because of
                # cloned projects.
                commits[commit['commit']['id:ID']] = commit['commit']
                #  Also relations may or may not be duplicate. We need to
                # deduplicate them by a tuple (type, start_id, end_id).
                add_rel_to_set(commit['authors'], contribute_relations)
                add_rel_to_set(commit['commits'], contribute_relations)
                add_rel_to_set(commit['belongs'], general_relations)
                contributors.update(commit['contributors'])
                for parent_relation in commit['parents']:
                    add_rel_to_set(parent_relation, general_relations)
            for package in packages:
                output.app(format_app(package))
                play_data = format_play_page(
                    package, input_dir, mtimes[package])
                output.play_page(play_data[0])
                output.general_relation(play_data[1])
            for tag_data in iter_tag_rows(repo_id, input_dir):
                output.tag(tag_data[0])
                output.general_relation(tag_data[1])
                output.general_relation(tag_data[2])
            for branch_data in iter_branch_rows(repo_id, input_dir):
                output.branch(branch_data[0])
                output.general_relation(branch_data[1])
                output.general_relation(branch_data[2])
            for paths in iter_implemented_rel(repo_id, input_dir):
                output.implemented_relation(paths)
        for contributor in contributors.values():
            output.contributor(contributor)
        for commit in commits.values():
            output.commit(commit)
        for relation in general_relations.values():
            output.general_relation(relation)
        for relation in contribute_relations.values():
            output.contribute_relation(relation)


def escape(string: str) -> str:
    """Escape newlines and special characters.

    Also strip at end of string because Neo4j import barks on it.
    """
    return string
    if not string:
        return ''
    return string.rstrip().encode('unicode_escape').decode()


class Neo4jDialect(csv.Dialect):
    """A CSV dialect that is compatible with Neo4j import tools."""
    delimiter = ','
    doublequote = True
    escapechar = '\\'
    lineterminator = '\n'
    quotechar = '"'
    quoting = csv.QUOTE_ALL
    skipinitialspace = False


class Output(object):
    """Combine all CSV writers in one class.

    Facilitates opening all writers simultaneously in one `with` statement.

    Example:

        with Output('output_dir/') as output:
            for row in repos:
                output.repo(row)
    """
    # pylint: disable = too-few-public-methods
    output_type = [
        ('repo', REPOSITORY_FIELDS),
        ('commit', COMMIT_FIELDS),
        ('app', APP_FIELDS),
        ('play_page', PLAY_PAGE_FIELDS),
        ('branch', BRANCH_FIELDS),
        ('tag', TAG_FIELDS),
        ('contributor', CONTRIBUTOR_FIELDS),
        ('general_relation', GENERAL_RELATION_FIELDS),
        ('contribute_relation', CONTRIBUTOR_RELATION_FIELDS),
        ('implemented_relation', IMPLEMENTED_RELATION_FIELDS),
    ]

    def __init__(self, directory: str):
        self.directory = directory
        self._output = {}
        for tag, fields in self.output_type:
            self._init_output(tag, fields)

    def __enter__(self):
        return self

    def __exit__(self, *exception_info):
        """Close all file handles."""
        for output in self._output.values():
            output['handle'].close()

    def __getattribute__(self, name):
        """Resolve tags in output_types to self.write.

        Allows self.repo(row) be resolved to self.write('repo', row)
        """
        if name in object.__getattribute__(self, '_output'):
            write = object.__getattribute__(self, 'write')
            return lambda row: write(name, row)
        return object.__getattribute__(self, name)

    def _init_output(self, tag: str, fields: list):
        """Creates csv.DictWriter and writes headers."""
        if tag == 'branch':
            filename = 'branches.csv'
        else:
            filename = '{}s.csv'.format(tag)
        path = os.path.join(self.directory, filename)
        output_file = open(path, 'w', newline='')
        writer = csv.DictWriter(output_file, fields, dialect=Neo4jDialect)
        writer.writeheader()
        self._output[tag] = {
            'handle': output_file,
            'writer': writer,
        }

    def write(self, tag: str, row: dict):
        """Write row to tagged CSV output."""
        if tag in self._output:
            self._output[tag]['writer'].writerow(row)
        else:
            raise KeyError('No writer for tag {}'.format(tag))


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Add arguments to parser."""
    parser.add_argument(
        'input_dir', type=str,
        help='Directory containing CSV and JSON files to convert.')
    parser.add_argument(
        'output_dir', type=str,
        help='Directory to store Neo4j import files in.')
    parser.set_defaults(func=_main)


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    __log__.info('------- Arguments: -------')
    __log__.info('input-dir: %s', args.input_dir)
    __log__.info('output-dir: %s', args.output_dir)
    __log__.info('------- Arguments end -------')
    prepare_for_neo4j_import(args.input_dir, args.output_dir)
