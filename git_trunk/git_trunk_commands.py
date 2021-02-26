"""Git Trunk based workflow helper commands."""
import re
from collections import namedtuple
from typing import Optional, Union
import natsort
from footil.path import chdir_tmp
from footil.patterns import MethodCommand
from footil import version as version_manager
import git  # GitPython

from . import git_trunk_base as gt_base
from . import git_trunk_config as gt_config

EMPTY_VERSION = '0.0.0'  # default version when are no versions yet

MethodData = namedtuple('MethodData', 'method args kwargs')
# Set defaults for args and kwargs.
MethodData.__new__.__defaults__ = ((), {})


class GitTrunkInit(gt_base.GitTrunkCommand):
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
        log_level: str = gt_base.DEFAULT_LOG_LEVEL,
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


class GitTrunkStart(
        gt_base.GitTrunkCommand, gt_base.GitTrunkReleaseHelperMixin):
    """Class to create branch like feature or release."""

    section = gt_config.START_SECTION

    def check_run(self, **kwargs):
        """Override to check if start can be run."""
        res = super().check_run(**kwargs)
        trunk_branch_name = self.config.base['trunk_branch']
        # Expecting active ref to be branch.
        active_branch_name = self.active_ref_name
        if active_branch_name != trunk_branch_name:
            raise ValueError(
                "To create new branch, you must be on trunk branch '%s'."
                " Currently on '%s'" % (trunk_branch_name, active_branch_name)
            )
        return res

    def _get_fetch_branches_pattern(self):
        pattern = self.config.section['fetch_branch_pattern']
        return pattern or gt_config.DEFAULT_FETCH_PATTERN

    def _fetch_branches(self):
        remote = self.remote_name
        pattern = self._get_fetch_branches_pattern()
        self.git.fetch(
            remote,
            'refs/heads/{pattern}:refs/remotes/{remote}/{pattern}'.format(
                pattern=pattern, remote=remote),
            _log_input=True,
            _log_output=True)

    def _get_branch_head_filters(self, pattern: Optional[str] = None) -> list:
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
        heads = gt_base.multi_filter(filters, self.remote_branch_heads)
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
            raise ValueError(gt_base._format_stderr(e.stderr))
        if set_upstream:
            if not self.remote_name:
                self.logger.warning(
                    "Missing remote to set upstream for '%s' branch. "
                    "Ignoring.", name)
            # -u is shortcut to set upstream.
            self.git_push(self.remote_name, name, '-u')  # type: ignore

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
            repo_path=self.repo.working_dir, log_level=self.logger.level)
        trunk_refresh.run()
        if not name:
            name = self._find_branch_name(pattern=pattern)
        self._create_branch(name, set_upstream=set_upstream)  # type: ignore


class GitTrunkFinish(
        gt_base.GitTrunkCommand, gt_base.GitTrunkReleaseHelperMixin):
    """Class to finish active branch on trunk branch."""

    section = gt_config.FINISH_SECTION

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
        if (self.config.section['require_squash'] and
                self.max_squash_commits_count):
            raise ValueError(
                "%s branch must be squashed first before finishing" %
                self.active_branch_name)
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
                            trunk_tracking_data.head,
                        )
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
                            active_tracking_data.head,
                        )
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


class GitTrunkRelease(gt_base.GitTrunkCommand):
    """Class to release new tag on trunk branch."""

    section = gt_config.RELEASE_SECTION

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
        p = gt_config.DEFAULT_FETCH_PATTERN
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
            gt_base._git_cmd(['tag'] + args + ['-m', msg])

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
        self._create_tag(version, ref)  # type: ignore
        self.commands_invoker.run()


class GitTrunkRefresh(gt_base.GitTrunkCommand):
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


class GitTrunkSquash(gt_base.GitTrunkCommand):
    """Class to allow squashing active branch N commits."""

    section = gt_config.SQUASH_SECTION

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
            self, message: Union[None, str]=None):
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
            repo_path=self.repo.working_dir, log_level=self.logger.level)
        trunk_refresh.run()
        message = self._get_message_for_squash(
            count,  # type: ignore
            include_squash_msg=include_squash_msg,
            custom_msg=custom_msg
        )
        self._squash(count)  # type: ignore
        self._amend_commit_for_squash(message=message)
        # To open commit message for editing.
        if self.config.section['edit_squash_message']:
            # Using subprocess to make sure editor is opened correctly.
            with chdir_tmp(self.repo.working_dir):
                gt_base._git_cmd(['commit', '--amend'])
        if self.config.section['force_push_squash']:
            tracking_data = self.active_tracking_branch_data
            if tracking_data:
                self.git_push(
                    tracking_data.remote, tracking_data.head, '--force'
                )
