"""Collect meta-data of commits, branches, and tags

When creating the Docker image with the graph database, access to Gitlab is
not available. Temporarily store all data in CSV files.

Use -h or --help for more information.
"""
import argparse
import csv
import itertools
import logging
import os
from typing import Dict, IO, Iterable, Iterator, List

from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Project

from util.bare_git import BareGit, GitHistory
from util.parse import parse_iso8601


__log__ = logging.getLogger(__name__)


GITLAB_HOST = 'http://145.108.225.21'
GITLAB_REPOSITORY_PATH = '/var/opt/gitlab/git-data/repositories/gitlab'


def iter_tags(gitlab_project: Project) -> Iterator[str]:
    """Iterator over tag meta-data in gitlab_project.

    :param gitlab.v4.object.Project gitlab_project:
        Gitlab project to retrieve branches from.
    :returns Iterator[str]:
        An iterator over tag data to store in CSV file.
    """
    for tag in gitlab_project.tags.list(all=True, as_list=False):
        yield {
            'commit_hash': tag.commit['id'],
            'tag_name': tag.name,
            'tag_message': tag.message,
            }


def iter_branches(gitlab_project: Project) -> Iterator[str]:
    """Iterator over branch meta-data in gitlab_project.

    :param gitlab.v4.object.Project gitlab_project:
        Gitlab project to retrieve branches from.
    :returns Iterator[str]:
        An iterator over branch data to store in CSV file.
    """
    for branch in gitlab_project.branches.list(all=True, as_list=False):
        yield {
            'commit_hash': branch.commit['id'],
            'branch_name': branch.name,
            }


def find_paths(pattern: str, file_pattern: str, branch: str, git: BareGit):
    """Find files in GIT repository.

    :param str pattern:
        Search pattern.
    :param str file_pattern:
        Pathspec to restrict files matched in GIT repository.
    :param str branch:
        Refspec to base search in GIT repository on.
    :param BareGit git:
        GIT repository to search.
    :returns List[str]:
        list of path names.
    """
    if not branch:
        __log__.warning('Branch is None for %s', git.git_dir)
        return []
    search_results = git.grep(pattern, branch, file_pattern, ['--name-only'])
    paths = sorted(map(lambda m: m[1], search_results))
    groups = itertools.groupby(paths)
    return [group[0] for group in groups]


def find_manifest_paths(
        package_name: str, branch: str, git: BareGit) -> List[str]:
    """Find paths of AndroidManifest.xml files in git repository.

    :param str package_name:
        Package name of :App node.
    :param str branch:
        Refspec to base search in GIT repository on.
    :param BareGit git:
        GIT repository to search.
    :returns List[str]:
        List of paths to AndroidManifest.xml files for package_name.
    """
    pattern = 'package="{}"'.format(package_name)
    return find_paths(pattern, '*AndroidManifest.xml', branch, git)


def find_gradle_config_paths(
        package_name: str, branch: str, git: BareGit) -> List[str]:
    """Find paths of gradle configuration files in git repository.

    :param str package_name:
        Package name of :App node.
    :param str branch:
        Refspec to base search in GIT repository on.
    :param BareGit git:
        GIT repository to search.
    :returns List[str]:
        List of paths to build.gradle files for package_name as applicationId.
    """
    pattern = 'applicationId *.{}.'.format(package_name)
    return find_paths(pattern, '*build.gradle', branch, git)


def find_maven_config_paths(
        package_name: str, branch: str, git: BareGit) -> List[str]:
    """Find paths of Maven configuration files in git repository.

    :param str package_name:
        Package name of :App node.
    :param str branch:
        Refspec to base search in GIT repository on.
    :param BareGit git:
        GIT repository to search.
    :returns List[str]:
        List of paths to pom.xml files with package name as groupId.
    """
    pattern = r'<groupId>{}<\/groupId>'.format(package_name)
    return find_paths(pattern, '*pom.xml', branch, git)


def iter_implementation_properties(
        project: Project, packages: List[str],
        git: BareGit) -> Iterator[Dict[str, str]]:
    """Iterator over package with paths found in project.

    Find Android manifest files and build system files for app in the
    repository.

    :param gitlab.v4.object.Project gitlab_project:
        Gitlab project to search.
    :param List[str] packages:
        A list of package names to be connected with the repository identified
        by repo_node_id.
    :param str gitlab_repo_prefix:
        Prefix to paths of bare Git repositories of Gitlab on disk.
    :returns Iterator[Dict[str, str]]:
        Iterator over dictionary with paths as comma separated lists.
    """
    for package in packages:
        manifest = find_manifest_paths(package, project.default_branch, git)
        gradle = find_gradle_config_paths(package, project.default_branch, git)
        maven = find_maven_config_paths(package, project.default_branch, git)
        yield {
            'package': package,
            'manifestPaths': ','.join(manifest),
            'gradleConfigPaths': ','.join(gradle),
            'mavenConfigPaths': ','.join(maven),
            }


def write_csv(
        prefix: str, filename: str, fieldnames: List[str],
        rows: Iterable[Dict[str, str]]):
    """Write CSV file."""
    path = os.path.join(prefix, filename)
    with open(path, 'w') as csv_file:
        csv_writer = csv.DictWriter(csv_file, fieldnames)
        csv_writer.writeheader()
        for row in rows:
            csv_writer.writerow(row)


def store_repository_info(csv_file: IO[str], gitlab: Gitlab, outdir: str):
    """Add data of GIT repositories to Neo4j.

    :param IO[str] csv_file:
        CSV file containing meta data of repositories.
    :param Neo4j neo4j:
        Neo4j instance to add nodes to.
    :param Gitlab gitlab:
        Gitlab instance to query repository data from.
    """
    csv_reader = csv.DictReader(csv_file)
    for row in csv_reader:
        __log__.info('Repo info: %s', (
            row['id'], row['full_name'],
            row['clone_project_id'], row['clone_project_path']))

        repo_dir = os.path.join(outdir, row['id'])
        os.makedirs(repo_dir)

        packages = row['packages'].split(',')

        try:
            project = gitlab.projects.get(int(row['clone_project_id']))
        except GitlabGetError as error:
            __log__.exception(
                'Could not get Gitlab project with ID: %s',
                row['clone_project_id'])
            __log__.error('These are repository details: %s', row)
            __log__.error('%s\n%s', error, error.response_body)
            continue

        repository_path = os.path.join(
            gitlab.repository_prefix, '{}.git'.format(project.path))
        __log__.info('Use local git repository at %s', repository_path)
        git = GitHistory(repository_path)

        write_csv(
            repo_dir, 'snapshot.csv',
            ['web_url', 'created_at'],
            [{'web_url': project.web_url, 'created_at': project.created_at}])

        write_csv(
            repo_dir, 'commits.csv',
            [
                'id', 'short_id', 'title', 'message', 'additions',
                'deletions', 'total', 'author_name', 'author_email',
                'committer_name', 'committer_email', 'authored_date',
                'committed_date', 'parent_ids'
            ],
            git.iter_commits())

        write_csv(
            repo_dir, 'branches.csv',
            ['commit_hash', 'branch_name'],
            iter_branches(project))

        write_csv(
            repo_dir, 'tags.csv',
            ['commit_hash', 'tag_name', 'tag_message'],
            iter_tags(project))

        write_csv(
            repo_dir, 'paths.csv',
            [
                'package', 'manifestPaths', 'gradleConfigPaths',
                'mavenConfigPaths'
            ],
            iter_implementation_properties(project, packages, git))


def define_cmdline_arguments(parser: argparse.ArgumentParser):
    """Add arguments to parser."""
    parser.add_argument('OUTDIR', type=str, help='Output directory')
    parser.add_argument(
        'REPOSITORY_LIST', type=argparse.FileType('r'),
        help='''CSV file that lists meta data for repositories and their
        snapshots on Gitlab.''')
    parser.add_argument(
        '--gitlab-repos-dir', type=str, default=GITLAB_REPOSITORY_PATH,
        help='''Local path to repositories of Gitlab user `gitlab`. Default:
        {}'''.format(GITLAB_REPOSITORY_PATH))
    parser.add_argument(
        '--gitlab-host', type=str, default=GITLAB_HOST,
        help='''Hostname Gitlab instance is running on. Default:
        {}'''.format(GITLAB_HOST))
    parser.set_defaults(func=_main)


def _main(args: argparse.Namespace):
    """Pass arguments to respective function."""
    __log__.info('------- Arguments: -------')
    __log__.info('OUTDIR: %s', args.OUTDIR)
    __log__.info('REPOSITORY_LIST: %s', args.REPOSITORY_LIST.name)
    __log__.info('--gitlab-repos-dir: %s', args.gitlab_repos_dir)
    __log__.info('--gitlab-host: %s', args.gitlab_host)
    __log__.info('------- Arguments end -------')

    gitlab = Gitlab(args.gitlab_host, api_version=4)
    gitlab.repository_prefix = args.gitlab_repos_dir

    store_repository_info(args.REPOSITORY_LIST, gitlab, args.OUTDIR)
