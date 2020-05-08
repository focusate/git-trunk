"""Git Trunk based workflow helper commands."""
import os
import abc
import re
import string
from collections import namedtuple
from typing import Optional, Union, Any, Iterable, List, Tuple
from configparser import NoSectionError, NoOptionError
import natsort
from footil.log import get_verbose_logger
from footil.path import chdir_tmp
from footil.formatting import format_func_input
from footil.patterns import MethodCommand, DequeInvoker
import git  # GitPython
import subprocess
import shutil

from . import version as version_manager

SEP = '"'
BASE_SECTION = 'trunk'
START_SECTION = 'start'
FINISH_SECTION = 'finish'
RELEASE_SECTION = 'release'
SQUASH_SECTION = 'squash'
SECTION_PATTERN = '{section} {sep}%s{sep}'.format(
    section=BASE_SECTION, sep=SEP)


EMPTY_VERSION = '0.0.0'  # default version when are no versions yet
LOG_INPUT = '_log_input'
LOG_OUTPUT = '_log_output'

DEFAULT_LOG_LEVEL = 'NOTICE'
DEFAULT_FETCH_PATTERN = '*'

# Object to store tracking data for upstream branch, if there is one.
TrackingBranchData = namedtuple('TrackingBranchData', 'remote head')
MethodData = namedtuple('MethodData', 'method args kwargs')
# Set defaults for args and kwargs.
MethodData.__new__.__defaults__ = ((), {})


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
def multi_filter(filters: Iterable[callable], items: Iterable) -> list:
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


class GitTrunkConfig:
    """Class to manage git-trunk configuration."""

    @staticmethod
    def _to_git_section(section: str) -> str:
        if section != BASE_SECTION:
            return SECTION_PATTERN % section
        return section

    @classmethod
    def get_option_vals(
            self, name, default, forced_type=None, label=None, description=''):
        """Get option values for config."""
        def get_label():
            if label:
                return label
            return string.capwords(name.replace('_', ' '))

        return {
            'name': name,
            'default': default,
            'forced_type': forced_type,
            'label': get_label(),
            'description': description,
        }

    @classmethod
    def get_config_struct(cls):
        """Get structure for setting and getting config."""
        return {
            BASE_SECTION: {
                'trunkbranch': cls.get_option_vals(
                    'trunk_branch',
                    'master',
                    forced_type=str,
                    description=(
                        "Trunk/Mainline branch name. Defaults to 'master'."
                    )
                ),
            },
            START_SECTION: {
                'fetchbranchpattern': cls.get_option_vals(
                    'fetch_branch_pattern',
                    DEFAULT_FETCH_PATTERN,
                    forced_type=str,
                    description=(
                        "Pattern used when fetching remote branches. "
                        "Defaults to {p} (fetch all "
                        "branches)'.".format(p=DEFAULT_FETCH_PATTERN)
                    )
                ),
            },
            FINISH_SECTION: {
                'ff': cls.get_option_vals(
                    'ff',
                    default=True,
                    label="Fast Forward Flag",
                    description="Whether to use --ff-only or --no-ff flag."
                ),
            },
            RELEASE_SECTION: {
                'versionprefix': cls.get_option_vals(
                    'version_prefix',
                    '',
                    forced_type=str,
                    description="Whether version prefix is to be used."
                ),
                'releasebranchprefix': cls.get_option_vals(
                    'release_branch_prefix',
                    'release/',
                    forced_type=str,
                    description="Release branch prefix. Defaults to 'release/'"
                ),
                'usesemver': cls.get_option_vals(
                    'use_semver',
                    default=True,
                    description="Whether semver versioning is to be used."
                ),
                'edittagmessage': cls.get_option_vals(
                    'edit_tag_message',
                    default=True,
                    description=(
                        "Whether editor should be opened for tag message"
                        " before creating tag for release."
                    )
                ),
            },
            SQUASH_SECTION: {
                'editsquashmessage': cls.get_option_vals(
                    'edit_squash_message',
                    default=True,
                    description=(
                        "Whether to open editor after squashing for"
                        " customizing message")
                ),
                'forcepushsquash': cls.get_option_vals(
                    'force_push_squash',
                    default=True,
                    description=(
                        "Whether to force push to remote tracking branch"
                        " after squashing."
                    )
                ),
            }
        }

    def handle_exception(
            self, exception: Exception, msg: str, section: str, option: str):
        """Handle exception when reading git configuration.

        Override if exception must be handled differently.
        """
        raise ValueError(msg)

    def get_value(
        self,
        cr: git.Repo.config_reader,
        git_section: str,
        option: str,
            vals: dict) -> Any:
        """Retrieve value from git config.

        Args:
            cr: config reader object to read git config.
            git_section: git config section.
            option: config section option.
            vals: config structure to handle read git config options.
        """
        try:
            val = cr.get_value(git_section, option)
            if vals.get('forced_type'):
                val = vals['forced_type'](val)
            return val
        # Re-raise with more meaningful description.
        except NoSectionError as e:
            return self.handle_exception(
                e,
                "%s section is missing in git configuration" % git_section,
                git_section,
                option)
        except NoOptionError as e:
            return self.handle_exception(
                e,
                "%s option is missing in git configuration %s section" % (
                    option, git_section),
                git_section,
                option,
            )

    def _get_config_template(self):
        return {
            section: {} for section in self.get_config_struct().keys()
        }

    def read(self) -> dict:
        """Return git-trunk configuration from git config file."""
        cfg = self._get_config_template()
        with self._config_reader() as cr:
            for section, section_struct in self.get_config_struct().items():
                # Convert to be more readable.
                for option, vals in section_struct.items():
                    git_section = self._to_git_section(section)
                    cfg[section][vals['name']] = self.get_value(
                        cr, git_section, option, vals)
        return cfg

    def write(self, config: dict) -> None:
        """Write specified config on git config file."""
        with self._config_writer() as cw:
            for section, section_cfg in config.items():
                for option, val in section_cfg.items():
                    git_section = self._to_git_section(section)
                    cw.set_value(git_section, option, val)

    def check_config(self, cfg: dict) -> None:
        """Check if got configuration is correct one.

        Override to implement specific checks.
        """
        return True

    def __init__(
        self,
        config_reader: git.Repo.config_reader,
        config_writer: git.Repo.config_writer,
            section) -> None:
        """Initialize git trunk configuration."""
        super().__init__()
        self._config_reader = config_reader
        self._config_writer = config_writer
        self._section = section
        self._config = None

    @property
    def sections(self) -> dict:
        """Use _get_config to get active git-trunk configuration.

        Returns full config.
        """
        if self._config is None:
            cfg = self.read()
            self.check_config(cfg)
            self._config = cfg
        return self._config

    @property
    def base(self):
        """Return base cfg part, not related with specific command."""
        return self.sections[BASE_SECTION]

    @property
    def section(self) -> dict:
        """Return rel section config to have shortcut most used cfg."""
        try:
            return self.sections[self._section]
        except KeyError:  # if command has no related section.
            raise Warning(
                "This configuration does not have main section specified")


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
        self.repo = git.Repo(_get_repo_path(repo_path=repo_path))
        self.git = self.repo.git()  # git command interface.
        self.logger = get_verbose_logger(__name__, log_level=log_level, fmt='')


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
            self.repo.config_reader,
            self.repo.config_writer,
            self.section
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
    def commands_invoker(self):
        """Return DequeInvoker object."""
        return self._commands_invoker

    @property
    def config(self) -> dict:
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

    def count_commits_behind_ahead(self, ref1, ref2) -> Tuple[int]:
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

    def pull_trunk_branch(self) -> None:
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


class GitTrunkInit(GitTrunkCommand):
    """Class to handle trunk configuration initialization."""

    def _prepare_init_config(self, kwargs) -> dict:
        """Init cfg struct with existing cfg (if any) for run method.

        Value is determined using this priority:
            1. Was passed directly in initialization.
            2. Was read from git config.
            3. Default value from config structure.
        """
        init_cfg = self.config._get_config_template()
        config = self.config
        for section, section_struct in self.config.get_config_struct().items():
            for option, vals in section_struct.items():
                name = vals['name']
                if kwargs.get(name) is not None:
                    val = kwargs[name]
                elif config.sections[section][name] is not None:
                    val = config.sections[section][name]
                else:
                    val = vals['default']
                init_cfg[section][option] = val
        return init_cfg

    def __init__(
        self,
        repo_path: Optional[str] = None,
        log_level: str = DEFAULT_LOG_LEVEL,
            **kwargs) -> None:
        """Override to include init options."""
        super().__init__(repo_path=repo_path, log_level=log_level)
        # Attaching different handle_exception method, because standard
        # one does not fit GitTrunkInit case (its simpler to hook this
        # method instead of creating different config class just for
        # that).
        self._config.handle_exception = self.handle_exception
        self._init_cfg = self._prepare_init_config(kwargs)

    def handle_exception(self, exception, msg, section, option):
        """Override to not raise exception.

        When reading configuration during first time during init,
        configuration won't be set yet, so returning None, to indicate
        no value exists for specific section/option yet.
        """
        return None

    def run(self, **kwargs) -> None:
        """Initialize git trunk configuration."""
        super().run(**kwargs)
        self.config.write(self._init_cfg)


class GitTrunkStart(GitTrunkCommand, GitTrunkReleaseHelperMixin):
    """Class to create branch like feature or release."""

    section = START_SECTION

    def check_run(self, **kwargs):
        """Override to check if start can be run."""
        res = super().check_run(**kwargs)
        trunk_branch_name = self.config.base['trunk_branch']
        active_branch_name = self.active_branch_name
        if active_branch_name != trunk_branch_name:
            raise ValueError(
                "To create new branch, you must be on trunk branch '%s'."
                " Currently on '%s'" % (trunk_branch_name, active_branch_name)
            )
        return res

    def _get_fetch_branches_pattern(self):
        pattern = self.config.section['fetch_branch_pattern']
        return pattern or DEFAULT_FETCH_PATTERN

    def _fetch_branches(self):
        remote = self.remote_name
        pattern = self._get_fetch_branches_pattern()
        self.git.fetch(
            remote,
            'refs/heads/{pattern}:refs/remotes/{remote}/{pattern}'.format(
                pattern=pattern, remote=remote),
            _log_input=True,
            _log_output=True)

    def _get_branch_head_filters(self, pattern: Optional[str] = None) -> tuple:
        def not_tracked_head_filter(head: str):
            return head not in tracked_heads

        def regex_head_filter(head: str):
            return re.search(pattern, head)

        tracked_heads = self.tracking_branch_map.values()
        filters = [not_tracked_head_filter]
        if pattern:
            filters.append(regex_head_filter)
        return filters

    def _find_branch_name(self, pattern: Optional[str] = None):
        if self.remote_name:
            self._fetch_branches()
        filters = self._get_branch_head_filters(pattern=pattern)
        heads = multi_filter(filters, self.remote_branch_heads)
        msg = "Can't find branch name to create locally."
        try:
            remote_head = natsort.natsorted(heads)[0]
        except IndexError:
            raise ValueError(msg)
        return remote_head

    def _create_branch(self, name: str, set_upstream: Optional[bool] = True):
        try:
            self.git.checkout('-b', name, _log_input=True, _log_output=True)
        except git.exc.GitCommandError as e:
            raise ValueError(_format_stderr(e.stderr))
        if set_upstream:
            if not self.remote_name:
                self.logger.warning(
                    "Missing remote to set upstream for '%s' branch. "
                    "Ignoring.", name)
            # -u is shortcut to set upstream.
            self.git_push(self.remote_name, name, '-u')

    def run(
        self,
        name: Optional[str] = None,
        pattern: Optional[str] = None,
        set_upstream: Optional[bool] = True,
            **kwargs) -> None:
        """Create branch using specified options.

        These commands will be run:
            - git pull --rebase REMOTE TRUNK
            - git fetch (using specified refspec pattern in config)
            - git checkout -b BRANCH
            - git push REMOTE BRANCH -u (if specified to set upstream)

        Args:
            name: custom name of the branch.
            pattern: regex pattern to filter existing remote branches.
                If custom name is not specified, will use this pattern
                on branch names.
            set_upstream: whether to set upstream after creating branch.

        """
        super().run(name=name, **kwargs)
        # Updating trunk so new branch created from it is up to date.
        trunk_refresh = GitTrunkRefresh(
            repo_path=self.repo.git_dir, log_level=self.logger.level)
        trunk_refresh.run()
        if not name:
            name = self._find_branch_name(pattern=pattern)
        self._create_branch(name, set_upstream=set_upstream)


class GitTrunkFinish(GitTrunkCommand, GitTrunkReleaseHelperMixin):
    """Class to finish active branch on trunk branch."""

    section = FINISH_SECTION

    def _get_ff_flag(self, ff) -> str:
        if ff:
            return '--ff-only'
        return '--no-ff'

    @property
    def ff_flag(self):
        """Return ff flag for git.

        no_ff is --no-ff flag, otherwise '--ff-only'.
        """
        return self._get_ff_flag(self.config.section['ff'])

    def _merge_branch(
            self, branch_name: str) -> None:
        self.git.merge(
            self.ff_flag, branch_name, _log_input=True, _log_output=True)

    def _check_remote_branch(
            self, remote_name: str, local_head: str, remote_head: str) -> None:
        self.git.fetch(remote_name, remote_head, _log_input=True)
        if self.git_diff(local_head, '%s/%s' % (remote_name, remote_head)):
            raise ValueError(
                "Local branch %s is not in sync with tracking branch %s on\n "
                "remote %s. You must first sync branch before finishing it." %
                (local_head, remote_head, remote_name)
            )

    def check_run(self, **kwargs):
        """Override to check if finish can be run."""
        res = super().check_run(**kwargs)
        trunk_branch_name = self.config.base['trunk_branch']
        if trunk_branch_name == self.active_branch_name:
            raise ValueError(
                "Branch to be finished must be different than trunk "
                "branch: %s" % trunk_branch_name)
        # If active branch is not ahead trunk branch. There is no point
        # to finish it (no new changes).
        if not self.count_commits_ahead_trunk():
            raise ValueError(
                "%s branch has no changes to be finished"
                " on %s." % (self.active_branch_name, trunk_branch_name))
        return res

    def run(self, **kwargs) -> None:
        """Merge active on trunk, push and then delete active branch.

        These git commands will be run:
            - git fetch REMOTE FEATURE
            - git checkout TRUNK
            - git merge FEATURE (-ff-only by default)
            - git push REMOTE
            - git push REMOTE --delete FEATURE
            - git branch -d FEATURE

        Branches that have release prefix, won't be merged on trunk.
        """
        def handle_tracking_data(
                branch_name, tracking_data, commands_data_list):
            remote = tracking_data.remote
            head = tracking_data.head
            self._check_remote_branch(remote, branch_name, head)
            for cd in commands_data_list:
                self.commands_invoker.add_command(
                    MethodCommand(cd.method, args=cd.args, kwargs=cd.kwargs))

        # Getting trunk branch remote first, to make sure we have
        # trunk branch.
        trunk_branch_name = self.config.base['trunk_branch']
        trunk_tracking_data = self.trunk_tracking_branch_data
        super().run(**kwargs)
        active_tracking_data = self.active_tracking_branch_data
        active_branch_name = self.active_branch_name
        self.git_checkout(trunk_branch_name)
        if trunk_tracking_data:
            handle_tracking_data(
                trunk_branch_name,
                trunk_tracking_data,
                [
                    MethodData(
                        method=self.git_push,
                        args=(
                            trunk_tracking_data.remote,
                            trunk_tracking_data.head)
                        )
                ]
            )
        if active_tracking_data:
            handle_tracking_data(
                active_branch_name,
                active_tracking_data,
                [
                    MethodData(
                        method=self.git_delete_remote_branch,
                        args=(
                            active_tracking_data.remote,
                            active_tracking_data.head)
                        )
                ]
            )
        force_delete = False
        if not self.is_release_branch(active_branch_name):
            self._merge_branch(active_branch_name)
        else:
            # Need to be explicit when deleting not merged branch.
            force_delete = True
        # Run pending commands in FIFO order.
        self.commands_invoker.run()
        self.git_delete_local_branch(
            active_branch_name, force=force_delete)


class GitTrunkRelease(GitTrunkCommand):
    """Class to release new tag on trunk branch."""

    section = RELEASE_SECTION

    def _get_default_tag_message(self, new_tag, ref, latest_tag=None):
        # If he have latest tag, we only add difference between latest
        # tag and trunk branch. If we don't have tag, we simply add all
        # changes, which we assume are not yet released.
        if latest_tag:
            ref = '%s..%s' % (latest_tag, ref)
        body = self.git.log(*['--oneline', ref])
        return "%s\n\n%s" % (new_tag, body)

    def __init__(self, *args, tag_msg_formatter=None, **kwargs):
        """Initialize trunk release attributes."""
        super().__init__(*args, **kwargs)
        self._tag_msg_formatter = (
            tag_msg_formatter or self._get_default_tag_message)
        if self.config.section['use_semver']:
            VersionManager = version_manager.SemverVersion
        else:
            VersionManager = version_manager.GenericVersion
        self._version_manager = VersionManager(self._get_versions)

    def _get_tags(self):
        tags = self.git.tag()
        if tags:
            return tags.split('\n')
        return []

    def _attach_prefix_to_version(self, version):
        return '%s%s' % (
            self.config.section['version_prefix'], version)

    def _detach_prefix_from_version(self, version):
        prefix = self.config.section['version_prefix']
        if version.startswith(prefix):
            return version[len(prefix):]
        return version

    def _map_versions_with_tags(self):
        return {
            self._detach_prefix_from_version(t): t for t in self._get_tags()
        }

    @property
    def versions_tags_map(self):
        """Return active versions with tags map.

        Versions are tag names without prefix. If prefix is not used,
        then version will match tag name.
        """
        return self._map_versions_with_tags()

    def _get_versions(self):
        return self.versions_tags_map.keys()

    @property
    def version_manager(self):
        """Return version manager object."""
        return self._version_manager

    def _fetch_tags(self):
        p = DEFAULT_FETCH_PATTERN
        self.git.fetch(
            self.remote_name,
            'refs/tags/{p}:refs/tags/{p}'.format(p=p),
            _log_input=True,
            _log_output=True)

    def _check_release(self, ref: Optional[str] = None):
        def has_unreleased_changes(latest_ver):
            if latest_ver == EMPTY_VERSION:
                # Means we have no versions yet - all existing changes
                # are not yet released.
                return True
            tag = self.versions_tags_map[latest_ver]
            target = ref or self.active_branch_name
            try:
                behind, ahead = self.count_commits_behind_ahead(tag, target)
            except git.exc.GitCommandError:
                raise ValueError(
                    "%s reference was not found. Make sure it is correct"
                    " commit hash or other reference." % ref)
            return ahead

        latest_ver = self.version_manager.get_latest_version()
        if not has_unreleased_changes(latest_ver):
            raise ValueError("There are no new changes to be released.")

    def _create_tag(self, new_version: str, ref: str):
        tag = self._attach_prefix_to_version(new_version)
        latest_ver = self.version_manager.get_latest_version()
        try:
            latest_tag = self.versions_tags_map[latest_ver]
        except KeyError:
            latest_tag = None
        msg = self._tag_msg_formatter(tag, ref, latest_tag=latest_tag)
        args = ['-a', tag, ref]  # tag on specific reference.
        if self.config.section['edit_tag_message']:
            args.append('--edit')
        # NOTE. this is fake command, because real one takes '-m' arg,
        # but we hide it on purpose, to not pollute logs.
        self.logger.notice('git tag %s', ' '.join(args))
        # Using subprocess, to make sure editor is opened correctly.
        with chdir_tmp(self.repo.working_dir):
            _git_cmd(['tag'] + args + ['-m', msg])

    def _push_tags(self):
        self.git.push('--tags', self.remote_name, _log_input=True)

    def check_run(self, **kwargs):
        """Override to check if release can be run."""
        res = super().check_run(**kwargs)
        if not kwargs.get('force'):
            self._check_release(ref=kwargs.get('ref'))
        return res

    def run(
        self,
        version: Optional[str] = None,
        ref: Optional[str] = None,
        force: Optional[bool] = False,
        part: Optional[str] = 'minor',
            **kwargs):
        """Create release tag for trunk branch.

        These commands will be run:
            - git fetch REMOTE 'refs/tags/*:refs/tags/*'
            - git tag -a TAG -m "MSG"
            - git push --tags

        Args:
            version: can specify custom version. If semver version is
                used, it must be valid semver version.
            ref: reference to add release on. If not set, will tag
                on latest active branch reference.
            force: allows to create tag for commit that is older (or the
                same) than latest tag points to.
            part: semver part to bump. Possible options:
                'major',
                'minor',
                'patch',
                'prerelease',
                'build'
                'final' - will remove prerelease/build parts.
        """
        ref = ref or self.active_branch_name
        if self.remote_name:
            self._fetch_tags()
            self.commands_invoker.add_command(MethodCommand(self._push_tags))
        super().run(
            version=version,
            ref=ref,
            force=force,
            part=part,
            **kwargs
        )
        version = self.version_manager.get_version(version, part=part)
        self._create_tag(version, ref)
        self.commands_invoker.run()


class GitTrunkRefresh(GitTrunkCommand):
    """Class to handle update trunk branch and rebase it on curr one."""

    def git_stash(self):
        """Stash active changes."""
        self.git.stash(_log_input=True, _log_output=True)

    def git_stash_apply(self):
        """Apply latest changes from stash."""
        self.git.stash('apply', _log_input=True, _log_output=True)

    def git_rebase_branch(self, target_branch: str):
        """Rebase target_branch on active branch."""
        self.git.rebase(target_branch, _log_input=True, _log_output=True)

    def run(self, **kwargs):
        """Update trunk branch and rebase it on active one.

        If active branch is trunk branch, branch will be updated from
        its remote only (if there is one).

        These commands will be run:
            - git stash (if needed)
            - git checkout TRUNK
            - git pull --rebase REMOTE TRUNK
            - git checkout ACTIVE
            - git rebase TRUNK
            - git stash apply (if needed)
        """
        super().run(**kwargs)
        # Using --ignore-submodules to avoid 'No stash entries found.'
        # due to the fact that submodule dir have changes
        if self.git.diff('--ignore-submodules'):
            self.git_stash()
            self.commands_invoker.add_command(
                MethodCommand(self.git_stash_apply))
        active_branch_name = self.active_branch_name
        trunk_branch_name = self.config.base['trunk_branch']
        if active_branch_name != trunk_branch_name:
            self.git.checkout(
                trunk_branch_name, _log_input=True, _log_output=True)
            # We will use LIFO priority to execute commands in correct
            # order, so git_checkout is added last, to be called
            # first.
            self.commands_invoker.add_command(
                MethodCommand(
                    self.git_rebase_branch, args=(trunk_branch_name,)
                )
            )
            self.commands_invoker.add_command(
                MethodCommand(self.git_checkout, args=(active_branch_name,))
            )
        self.pull_trunk_branch()
        self.commands_invoker.run(priority='lifo')


class GitTrunkSquash(GitTrunkCommand):
    """Class to allow squashing active branch N commits."""

    section = SQUASH_SECTION

    @property
    def max_squash_commits_count(self):
        """Return maximum commits count that can be squashed."""
        return self.count_commits_ahead_trunk() - 1

    @property
    def head_hash(self):
        """Return HEAD hash."""
        return self.git.rev_parse('HEAD')

    def _get_n_logs_body(self, count: int):
        return self.git.log(
            '--format=%B', 'HEAD~%s..%s' % (count, self.head_hash))

    def _squash(self, count: int):
        self.git.reset('--soft', 'HEAD~%s' % count, _log_input=True)

    def _get_message_for_squash(
        self,
        squash_count: int,
        include_squash_msg: bool = True,
            custom_msg: str = ''):
        if custom_msg:
            return custom_msg
        if include_squash_msg:
            # Include one extra commit, to also have message from commit
            # that will be left after squashing.
            return self._get_n_logs_body(squash_count + 1)
        return None

    def _amend_commit_for_squash(
            self, message: Union[None, str] = None):
        args = ['--amend']
        if message:
            args.extend(['-m', message])
        else:
            args.append('--no-edit')
        self.git.commit(*args)

    def check_run(self, count: int = 1, **kwargs):
        """Override to check if squash can be run."""
        res = super().check_run(count=count, **kwargs)
        trunk_branch_name = self.config.base['trunk_branch']
        if trunk_branch_name == self.active_branch_name:
            raise ValueError(
                "Branch to be squashed must be different than trunk "
                "branch: %s" % trunk_branch_name)
        if self.git.diff('--stat'):
            raise ValueError(
                "There are uncommitted changes. To squash, first stash"
                " changes or commit them.")
        max_count = self.max_squash_commits_count
        if max_count <= 0:
            raise ValueError("No Commits to squash.")
        if count > max_count:
            raise ValueError(
                "You can squash maximum %s commits. You are trying to "
                "squash %s commits." % (max_count, count)
            )
        return res

    def run(
        self,
        count: int = None,
        include_squash_msg=True,
        custom_msg: str = '',
            **kwargs) -> None:
        """Squash active branch N commits.

        Args:
            count: number of commits to squash. If not specified, will
                squash all ahead commits leaving just the first one.
            include_squash_msg: whether to include squashed commits
                message.
            custom_msg: whether to use custom commit message after
                squash.

        These commands will be run:
            - git checkout TRUNK
            - git pull --rebase REMOTE TRUNK
            - git checkout ACTIVE
            - git rebase TRUNK
            - git reset --soft HEAD~COUNT
            - git commit --amend -m 'MSG' (message depends on options)
            - git push --force (if enabled in config)
        """
        if not count:
            count = self.max_squash_commits_count
        super().run(count=count, **kwargs)
        # Making sure active branch has all latest changes from trunk.
        trunk_refresh = GitTrunkRefresh(
            repo_path=self.repo.git_dir, log_level=self.logger.level)
        trunk_refresh.run()
        message = self._get_message_for_squash(
            count,
            include_squash_msg=include_squash_msg,
            custom_msg=custom_msg
        )
        self._squash(count)
        self._amend_commit_for_squash(message=message)
        # To open commit message for editing.
        if self.config.section['edit_squash_message']:
            # Using subprocess to make sure editor is opened correctly.
            with chdir_tmp(self.repo.working_dir):
                _git_cmd(['commit', '--amend'])
        if self.config.section['force_push_squash']:
            tracking_data = self.active_tracking_branch_data
            if tracking_data:
                self.git_push(
                    tracking_data.remote, tracking_data.head, '--force'
                )
