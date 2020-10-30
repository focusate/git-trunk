"""Git Trunk base classes for specific commands.

Defines base git command features.
"""
import os
import abc
from collections import namedtuple
from typing import Optional, Union, Any, Iterable, List, Tuple, Callable
from footil.log import get_verbose_logger
from footil.formatting import format_func_input
from footil.patterns import DequeInvoker
import git  # GitPython
import subprocess
import shutil

from .git_trunk_config import GitTrunkConfig, RELEASE_SECTION

LOG_INPUT = '_log_input'
LOG_OUTPUT = '_log_output'

DEFAULT_LOG_LEVEL = 'NOTICE'

# Object to store tracking data for upstream branch, if there is one.
TrackingBranchData = namedtuple('TrackingBranchData', 'remote head')


def _is_submodule(path_root, path_current):
    return path_root != path_current


def _get_repo_path(repo_path: Optional[str] = None) -> str:
    return repo_path or os.getcwd()


def _format_stderr(stderr) -> str:
    return stderr.replace('stderr: ', '')


def _git_cmd(args):
    """Call git via subprocess directly.

    Used when gitPython can't handle some cases correctly (like open
    terminal editors such as nano).
    """
    return subprocess.run([shutil.which('git')] + args)


# TODO: maybe worth to reuse on footil?
def multi_filter(filters: Iterable[Callable], items: Iterable) -> list:
    """Combine multiple condition functions to check all of them.

    All filter conditions must be satisfied for item to be included.

    Args:
        filters: condition functions to be combined.
        items: items to be filtered.

    Returns:
        list

    """
    def check_filters(item: Any):
        return all(f(item) for f in filters)

    return [i for i in items if check_filters(i)]


class GitTrunkReleaseHelperMixin:
    """Release management helper mixin for other command classes.

    Used to share common release helper functions for actions like
    finish, release.
    """

    def is_release_branch(self, branch_name: str) -> bool:
        """Check if branch is considered release branch."""
        prefix = self.config.sections[RELEASE_SECTION]['release_branch_prefix']
        if prefix:
            return branch_name.startswith(prefix)
        return False


class BaseGitTrunk(abc.ABC):
    """Base class for all git-trunk classes."""

    def __init__(
            self,
            repo_path: Optional[str] = None,
            log_level: str = DEFAULT_LOG_LEVEL) -> None:
        """Initialize git trunk class."""
        # calling to make sure MRO is handled correctly with multiple
        # inheritance.
        super().__init__()
        self._repo = git.Repo(_get_repo_path(repo_path=repo_path))
        self._git = self.repo.git()  # git command interface.
        self._repo_root = None
        self.logger = get_verbose_logger(__name__, log_level=log_level, fmt='')

    @property
    def repo(self) -> git.Repo:
        """Return current repository object."""
        return self._repo

    @property
    def git(self) -> git.cmd.Git:
        """Return current repository git command object."""
        return self._git

    def _get_path_parent_repo(self, git_cmd) -> str:
        """Return parent repo if current working dir is submodule."""
        return git_cmd.rev_parse('--show-superproject-working-tree')

    def _get_path_root_repo(self, git_cmd) -> str:
        """Traverse repositories tree up to root.

        Returned path is root repo path, which is main repo (not
        submodule).
        """
        path_parent = self._get_path_parent_repo(git_cmd)
        if path_parent:
            # Instantiating git command to use new parent path, because
            # gitPython uses saved path instead of current directory.
            return self._get_path_root_repo(git.Repo(path_parent).git())
        return git_cmd.working_dir

    @property
    def repo_root(self):
        """Parent repo to current repo.

        If it has no parent repo, it means this is root repo.
        """
        if not self._repo_root:
            prr = self._get_path_root_repo(self.git)
            # Can't use is_submodule property yet, because _repo_root
            # is not yet set.
            is_sub = _is_submodule(prr, self.repo.working_dir)
            # If working dir is root (not submodule), we just reference
            # existing repo object (no point creating new).
            self._repo_root = git.Repo(prr) if is_sub else self.repo
        return self._repo_root

    @property
    def is_submodule(self) -> bool:
        """Return True if working_dir is submodule, False otherwise."""
        return _is_submodule(self.repo_root.working_dir, self.repo.working_dir)


class GitTrunkCommand(BaseGitTrunk):
    """Command class to handle git trunk based workflow.

    Must be inherited by all command classes.
    """

    section = None

    def _hook_log_git_commands(self):
        def _call_process(self_inner, method, *args, **kwargs):
            # Removing output before input, to make sure its not
            # included in input logging.
            log_output = LOG_OUTPUT in kwargs and kwargs.pop(LOG_OUTPUT)
            if LOG_INPUT in kwargs and kwargs.pop(LOG_INPUT):
                dashified_method = git.cmd.dashify(method)
                pattern, pattern_args = format_func_input(
                    dashified_method,
                    command=True,
                    prefix='git ',
                    args=args,
                    kwargs=kwargs)
                self.logger.notice(pattern, *pattern_args)
            output = old_call_process(self_inner, method, *args, **kwargs)
            if log_output:
                self.logger.info(output)
            return output
        old_call_process = git.cmd.Git._call_process
        git.cmd.Git._call_process = _call_process

    def __init__(self, *args, **kwargs):
        """Initialize trunk command class attributes."""
        super().__init__(*args, **kwargs)
        self._commands_invoker = DequeInvoker()
        self._hook_log_git_commands()
        self._config = GitTrunkConfig(
            self.repo_root.config_reader,
            self.repo_root.config_writer,
            self.section,
            path_section=self.relpath_submodule
        )

    def get_branch_obj(self, branch_name: str) -> git.refs.head.Head:
        """Return branch object using branch name."""
        try:
            return self.repo.branches[branch_name]
        except IndexError:
            raise ValueError("%s branch was not found" % branch_name)

    def _get_tracking_branch_data(
        self,
        tracking_branch: git.refs.remote.RemoteReference) -> Union[
            TrackingBranchData, bool]:
        try:
            return TrackingBranchData(
                remote=tracking_branch.remote_name,
                head=tracking_branch.remote_head
            )
        # Handle case, when branch does not have tracking_branch, thus
        # tracking_branch is just None, which of course won't have any
        # attributes.
        except AttributeError:
            return False

    def is_symbolic_ref(
            self, ref: Union[git.Head, git.RemoteReference]) -> bool:
        """Check if reference is symbolic or real."""
        # Symbolic reference points to other reference or real one.
        # Real one throws exception when trying to get its
        # reference.
        try:
            ref.ref
            return True
        except TypeError:  # not pointing to anything, means real.
            return False

    @property
    def relpath_submodule(self) -> Union[str, None]:
        """Return relative submodule path from root repo path.

        If working path is not submodule path, returns None.
        """
        if not self.is_submodule:
            return None  # To be explicit
        return os.path.relpath(
            self.repo.working_dir, self.repo_root.working_dir
        )

    @property
    def commands_invoker(self):
        """Return DequeInvoker object."""
        return self._commands_invoker

    @property
    def config(self) -> GitTrunkConfig:
        """Return GitTrunkConfig instance."""
        return self._config

    @property
    def active_branch(self) -> git.Head:
        """Return active branch object."""
        return self.repo.active_branch

    @property
    def active_branch_name(self) -> str:
        """Return active branch name."""
        return self.active_branch.name

    @property
    def active_ref_name(self) -> str:
        """Return active reference.

        Active ref order is this:
            - branch
            - tag
            - commit
        """
        try:
            return self.active_branch.name
        except TypeError:
            try:
                return self.git.describe('--tags', '--exact-match')
            except git.exc.GitCommandError:
                return self.git.rev_parse('HEAD')

    @property
    def local_branch_names(self) -> List[str]:
        """Return current local branch names."""
        return [
            branch.name for branch in self.repo.branches if not
            self.is_symbolic_ref(branch)
        ]

    @property
    def remote_branch_heads(self) -> List[str]:
        """Return current remote branch heads."""
        remote = self.remote_name
        # Head is usually equivalent to local branch name.
        return [
            ref.remote_head for ref in self.repo.remotes[remote].refs if not
            self.is_symbolic_ref(ref)
        ]

    @property
    def tracking_branch_map(self) -> dict:
        """Return local branches mapped with their tracking branches."""
        map_ = {}
        for branch in self.repo.branches:
            tracking_data = self._get_tracking_branch_data(
                branch.tracking_branch()
            )
            if tracking_data:
                map_[branch.name] = tracking_data.head
            else:
                map_[branch.name] = None
        return map_

    @property
    def active_tracking_branch_data(self) -> Union[TrackingBranchData, bool]:
        """Return active branch remote name with remote branch name.

        If tracking branch/upstream is not set, will return False
        instead.
        """
        return self._get_tracking_branch_data(
            self.active_branch.tracking_branch()
        )

    @property
    def trunk_tracking_branch_data(self) -> Union[TrackingBranchData, bool]:
        """Return trunk branch remote name with remote branch name.

        If tracking branch/upstream is not set, will return False
        instead.
        """
        trunk_branch = self.get_branch_obj(
            self.config.base['trunk_branch'])
        return self._get_tracking_branch_data(trunk_branch.tracking_branch())

    @property
    def remote_name(self) -> Union[str, bool]:
        """Return active branch remote name from tracking branch.

        If there is no tracking branch for active branch, it will
        default to trunk tracking branch info.
        """
        data = self.active_tracking_branch_data
        if not data:  # default to trunk branch remote if there is one
            data = self.trunk_tracking_branch_data
            if not data:
                return False
        return data.remote

    def count_commits_behind_ahead(self, ref1, ref2) -> Tuple[int, int]:
        """Compare two refs and return count of commits behind/ahead."""
        compare = '%s..%s' % (ref1, ref2)
        res = self.git.rev_list(compare, '--left-right', '--count', )
        behind_ahead = res.split('\t')
        behind = int(behind_ahead[0])
        ahead = int(behind_ahead[1])
        return behind, ahead

    def count_commits_ahead_trunk(self) -> int:
        """Count commits ahead trunk branch."""
        behind, ahead = self.count_commits_behind_ahead(
            self.config.base['trunk_branch'], self.active_branch_name)
        return ahead

    def count_commits_behind_trunk(self) -> int:
        """Count commits behind trunk branch."""
        behind, ahead = self.count_commits_behind_ahead(
            self.config.base['trunk_branch'], self.active_branch_name)
        return behind

    @property
    def max_squash_commits_count(self):
        """Return maximum commits count that can be squashed."""
        return self.count_commits_ahead_trunk() - 1

    def git_diff(self, ref1, ref2, *args) -> str:
        """Return difference between two refs."""
        return self.git.diff('%s..%s' % (ref1, ref2), *args)

    def git_checkout(self, branch_name: str) -> None:
        """Checkout to specified branch."""
        self.git.checkout(branch_name, _log_input=True, _log_output=True)

    def git_push(self, remote_name: str, remote_head: str, *args) -> None:
        """Push active branch to remote."""
        self.git.push(*args, remote_name, remote_head, _log_input=True)

    def git_delete_remote_branch(
            self, remote_name: str, remote_head: str) -> None:
        """Delete specified branch on remote."""
        self.git.push(remote_name, '--delete', remote_head, _log_input=True)
        # TODO: push does not give any output. How to get output for it?
        self.logger.info(" - [deleted]         %s", remote_head)

    def git_delete_local_branch(self, branch_name: str, force=False) -> None:
        """Delete specified branch locally."""
        d = '-D' if force else '-d'
        self.git.branch(d, branch_name, _log_input=True, _log_output=True)

    def pull_trunk_branch(self) -> bool:
        """Pull trunk branch locally."""
        tracking_data = self.trunk_tracking_branch_data
        if not tracking_data:
            self.logger.notice(
                "No tracking branch for %s branch to pull. Ignoring.",
                self.config.base['trunk_branch'])
            return False
        self.git.pull(
            '--rebase',
            tracking_data.remote,
            tracking_data.head,
            _log_input=True,
            _log_output=True
        )
        return True

    def check_run(self, **kwargs) -> bool:
        """Check if run method can be called.

        Override to implement specific checks.
        """
        return True

    @abc.abstractmethod
    def run(self, **kwargs) -> None:
        """Run action. Must be implemented."""
        self.check_run(**kwargs)
