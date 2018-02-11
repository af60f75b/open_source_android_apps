"""Interact with a bare Git repository."""
from datetime import datetime
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
    COMMAND_LOG = 'log'
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
        try:
            return subprocess.run(
                command, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                shell=True, universal_newlines=False)  # TODO: errors='replace'
        except UnicodeDecodeError as error:
            __log__.exception(
                'Cannot decode to %s git output from command: %s',
                error.encoding, command)
            __log__.warn(
                'This was the object we failed to decode:\n%s',
                error.object)
            raise error

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
        try:
            for line in output.splitlines():
                match = self.REGEX_GREP_OUTPUT.match(line.decode())
                # TODO: Find out how to match the colon at the beginning of the
                #       non-capturing group, so that match.group(3) does not
                #       contain the initial colon.
                yield (match.group(1), match.group(2), match.group(3).lstrip(':'))
        except UnicodeDecodeError as error:
            __log__.exception(
                'Cannot decode to %s: %s', error.encoding, error.object)
            __log__.debug('Entire command output was:\n%s', output)
            raise error

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

    def log(self, options=None, git_options=None):
        """git-log wrapper."""
        output, status = self.git(self.COMMAND_LOG, options, git_options)
        return output


class GitHistory(BareGit):
    """Provides parsed access to commit history."""
    STATS_REGEX = re.compile(
        r'(?: ([0-9]+) files? changed)(?:, ([0-9]+) insertions?...)?'
        r'(?:, ([0-9]+) deletions?...)?')
    FORMAT_OPTION = (
        r"--pretty='format:"
            r'%n------%n'  # Commit separator
            r'id:%H%n'
            r'short_id:%h%n'
            r'parent_ids:%P%n'
            r'author_name:%an%n'
            r'author_email:%ae%n'
            r'authored_date:%ad%n'
            r'committer_name:%cn%n'
            r'committer_email:%ce%n'
            r'committed_date:%cd%n'
            r'title:%s%n'
            r'---%n'  # Message separator
            r'%w(0,4,4)%B%w(0,0,0)%n'  # Message indented by 4 spaces
            r"---%n'"
    )
    HISTORY_OPTIONS = ['--all', '--date=raw', '--shortstat', FORMAT_OPTION]

    def iter_commits(self):
        """Iterates over all commits in the Git repository."""
        # Strip all line feed characters to avoid polution of meta data.
        output = self._log_all()  #.replace(b'\r', b'')
        self.output = output
        for commit in output.split(b'\n------\n'):
            self.commit = commit
            if commit:
                parsed = self._parse_commit(commit)
                if 'WinRt' in parsed:
                    yield commit
                    break
                yield parsed

    def _log_all(self, start=None) -> bytes:
        """Run git-log with GitHistory.OPTIONS."""
        return self.log(options=self.HISTORY_OPTIONS)

    @staticmethod
    def _parse_commit(commit_str: bytes) -> dict:
        """Parse git-log output of one commit."""
        meta, message, stats = commit_str.split(b'\n---\n')
        try:
            commit = GitHistory._parse_meta(meta)
            commit['message'] = GitHistory._unindent_message(message).decode(
                errors='replace')
            commit.update(GitHistory._parse_stats(stats.decode()))
            return commit
        except UnicodeDecodeError as error:
            __log__.exception(
                'Cannot decode to %s output: %s', error.encoding, error.object)
            raise error

    @staticmethod
    def _parse_meta(input_str: bytes) -> dict:
        """Parse commit produced by git-log with FORMAT_OPTION."""
        commit = {}
        for line in input_str.split(b'\n'):
            if not line.strip():
                continue
            key, value = line.split(b':', 1)
            # Decode after splitting at colon because some non-ascii
            # characters appear to work as line feeds and remove the
            # colon.
            key = key.decode(errors='replace')
            value = value.decode(errors='replace')
            if key.endswith('_date'):
                value = GitHistory._raw_date_to_timestamp(value)
            if key == 'parent_ids':
                value = value.replace(' ', ',')
            commit[key] = value
        return commit

    @staticmethod
    def _parse_stats(stats_str: str) -> dict:
        r"""Parse --shorstat output.

        Example:
        >>> stats = ' 1 file changed, 104 insertions(+), 22 deletions(-)\n'
        >>> expected = {'additions': 104, 'total': 126, 'deletions': 22}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = ' 19 files changed, 2606 deletions(-)\n'
        >>> expected = {'additions': 0, 'total': 2606, 'deletions': 2606}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = ' 1 file changed, 5 insertions(+), 4 deletions(-)\n'
        >>> expected = {'additions': 5, 'total': 9, 'deletions': 4}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = ' 1 file changed, 21 insertions(+)\n'
        >>> expected = {'additions': 21, 'total': 21, 'deletions': 0}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = '\n 1 file changed, 21 insertions(+)\n'
        >>> expected = {'additions': 21, 'total': 21, 'deletions': 0}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = ' 1 file changed, 1 insertion(+), 3 deletions(-)\n'
        >>> expected = {'additions': 1, 'total': 4, 'deletions': 3}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = ' 1 file changed, 4 insertions(+), 1 deletion(-)\n'
        >>> expected = {'additions': 4, 'total': 5, 'deletions': 1}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = '      '
        >>> expected = {'additions': 0, 'total': 0, 'deletions': 0}
        >>> expected == GitHistory._parse_stats(stats)
        True
        >>> stats = '\n\n\n'
        >>> expected = {'additions': 0, 'total': 0, 'deletions': 0}
        >>> expected == GitHistory._parse_stats(stats)
        True
        """
        for line in stats_str.splitlines():
            match = GitHistory.STATS_REGEX.match(line)
            if match:
                additions = int(match.group(2) or 0)
                deletions = int(match.group(3) or 0)
                return {
                    'additions': additions,
                    'deletions': deletions,
                    'total': additions + deletions,
                }
        return {'additions': 0, 'deletions': 0, 'total': 0}

    @staticmethod
    def _unindent_message(message: bytes, level=4) -> bytes:
        r"""Remove level characters at beginning of every line.

        Example:
        >>> GitHistory._unindent_message(b'    foo bar')
        b'foo bar'
        >>> GitHistory._unindent_message(b'foo bar', 2)
        b'o bar'
        >>> msg = b'    foo\n        bar\n    baz'
        >>> expected = b'foo\n    bar\nbaz'
        >>> GitHistory._unindent_message(msg) == expected
        True
        >>> GitHistory._unindent_message(b'')
        b''
        >>> GitHistory._unindent_message(b' \n ')
        b'\n'
        >>> b'\rfoo' == GitHistory._unindent_message(b'    \rfoo')
        True
        """
        return b'\n'.join([
            # Only split at \n characters which git inserted.
            # Keep \r. They will be converted when decoding.
            line[level:] for line in message.split(b'\n')
        ])

    def _raw_date_to_timestamp(date_str: str) -> int:
        """Parse raw date and turn it into POSIX timestamp.

        Example:
        >>> date = '1518046601 +0100'
        >>> GitHistory._raw_date_to_timestamp(date)
        1518046601
        """
        return int(date_str.split()[0])


"""
git = GitHistory('/var/opt/gitlab/git-data/repositories/gitlab/nidzo732_securemessaging.git')
git = GitHistory('/var/opt/gitlab/git-data/repositories/gitlab/deviceconnect_deviceconnect-android.git')
problem = None
try:
    for commit in git.iter_commits():
        problem = commit
except ValueError as error:
    __log__.exception('error')
    problem = error
"""

if __name__ == "__main__":
    import doctest
    doctest.testmod()
