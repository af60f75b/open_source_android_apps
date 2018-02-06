"""Interact with a bare Git repository."""
import logging
import re
import subprocess


__log__ = logging.getLogger(__name__)


class BareGit(object):
    """BareGit facilitates interaction with bare Git repositories.

    Git commands can be executed on bare repositories without a working
    directory.

    The general `git` command and `git grep` are currently implemented.

    :param str repository:
        Path to Git repository. E.g. /home/user/my_project.git
    """
    BIN_GIT = '/usr/bin/git'
    OPTION_GIT_DIR = '--git-dir'
    OPTION_BARE = '--bare'
    OPTION_PATTERN = '-e'
    OPTIONS_END = '--'
    COMMAND_GREP = 'grep'
    REGEX_GREP_OUTPUT = re.compile(r'^([^:]*):([^:]*)(?:(.*))$')

    def __init__(self, repository):
        self.git_dir = repository
        self.git_options = [
            self.OPTION_GIT_DIR, self.git_dir, self.OPTION_BARE]

    @staticmethod
    def _format_command(
            command='', options=None, git_options=None, executable=BIN_GIT):
        """Turn command and arguments into a string.

        Grepping bare repositories works only with `shell=True` which accepts
        The entire command including arguments as one string.

        :param str command:
            The git subcommand. E.g. status
        :param list options:
            Options to the subcommand in a list.
        :param list git_options:
            Options to the git commands (inserted before the subcommand).
        :param str executable:
            Executable to run.
        :returns str:
            A complete command including arguments in the form:
            {executable} {git_options} {command} {options}
        """
        if not options:
            options = []
        if not git_options:
            git_options = []
        return '{executable} {git_options} {command} {options}'.format(
            executable=executable, git_options=' '.join(git_options),
            command=command, options=' '.join(options))

    def execute(self, command):
        """Execute a command.

        Use subprocess.run with pipes attached and shell=True.

        :param str command:
            Entire command to execute, including options as a string.
        :returns subprocess.CompletedProcess:
            The completed process.
        """
        return subprocess.run(
            command, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
            shell=True, universal_newlines=True)

    def git(self, command, options=None, git_options=None):
        """Execute Git command on the bare repository.

        :param str command:
            Git subcommand.
        :param list options:
            List of options to the subcommand.
        :param list git_options:
            Additional options to git.
        :returns Tuple[str, int]:
            A tuple containign output and return code.
            E.g. (stdout, 0) if process finished successfully.
        """
        if not git_options:
            git_options = []
        git_command = self._format_command(
            command, options, self.git_options + git_options, self.BIN_GIT)
        result = self.execute(git_command)
        if result.returncode:
            __log__.debug(
                'Git command returned status %d.\ncommand: %s\nstderr: %s',
                result.returncode, git_command, result.stderr)
        return result.stdout, result.returncode

    def _parse_grep_output(self, output):
        """Turn git grep output into tuples of (ref, path, match)."""
        for line in output.splitlines():
            match = self.REGEX_GREP_OUTPUT.match(line)
            # TODO: Find out how to match the colon at the beginning of the
            #       non-capturing group, so that match.group(3) does not
            #       contain the initial colon.
            yield (match.group(1), match.group(2), match.group(3).lstrip(':'))

    @staticmethod
    def _avoid_glob(argument):
        """Surround argument with single quotes to avoid globbing."""
        return "'{}'".format(argument)

    def grep(
            self, pattern, treespec, pathspec='', options=None,
            git_options=None):
        """Search a git repository.

        Execute `git grep` on the bare repository.

        Example:
        >>> git = BareGit('/tmp/test_repo.git')
        >>> list(git.grep('Hello', 'master'))
        [('master', 'test.txt', 'Hello Universe')]
        >>> list(git.grep('not existent search term', 'master'))
        []

        :param str pattern:
            The search pattern.
        :param str treespec:
            A treespec to search, e.g. a branch or a commit hash.
        :param str pathspec:
            An optional constraint on which files to search.
        :param list options:
            List of options to the subcommand.
        :param list git_options:
            Additional options to git.
        :returns Generator[Tuple[str, str, str]]:
            A generator of tuples containing the refspec, patch and matching
            text of a search result.
        """
        if not options:
            options = []
        if not git_options:
            git_options = []
        options += [self.OPTION_PATTERN, self._avoid_glob(pattern), treespec]
        if pathspec:
            options += [self.OPTIONS_END, self._avoid_glob(pathspec)]
        output, status = self.git(self.COMMAND_GREP, options, git_options)
        if status == 1:
            __log__.info('Status code 1: git grep returned no results')
        return self._parse_grep_output(output)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
