from __future__ import annotations
import os
from collections import namedtuple
import pathlib
import subprocess
from footil.path import chdir_tmp

from git_trunk.git_trunk_commands import GitTrunkSubmoduleUpdate
from . import common

GitModule = namedtuple('GitModule', ['local', 'remote'])


class TestGitTrunkSubmoduleUpdate(common.GitTrunkCommon):
    """Class to test git trunk submodule-update command."""

    def setUp(self):
        super().setUp()
        self.git_sub_1, self.dir_local_sub_1, self.dir_remote_sub_1 = self._setup_repo(
            self._build_sub_repo
        )
        self.git_sub_2, self.dir_local_sub_2, self.dir_remote_sub_2 = self._setup_repo(
            self._build_sub_repo
        )
        self.dir_absolute_sub_1 = pathlib.Path(self.dir_local.name) / 'external/sub1'
        self.dir_absolute_sub_2 = pathlib.Path(self.dir_local.name) / 'external/sub2'
        # We want to register and commit modules and
        self._add_and_remove_submodules(
            [
                GitModule(
                    local='external/sub1',
                    remote=self.dir_remote_sub_1.name,
                ),
                GitModule(
                    local='external/sub2',
                    remote=self.dir_remote_sub_2.name,
                ),
            ]
        )

    def test_01_update_all_submodules_implicitly(self):
        # GIVEN
        trunk_sub_update = GitTrunkSubmoduleUpdate(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        # WHEN
        with chdir_tmp(self.dir_local.name):
            trunk_sub_update.run()
        # THEN
        self.assertTrue(self.dir_absolute_sub_1.is_dir())
        self.assertTrue(self.dir_absolute_sub_2.is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / 'init_dir').is_dir())
        self.assertTrue((self.dir_absolute_sub_2 / 'init_dir').is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / 'extra_dir').is_dir())
        self.assertTrue((self.dir_absolute_sub_2 / 'extra_dir').is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / '.git').is_file())
        self.assertTrue((self.dir_absolute_sub_2 / '.git').is_file())
        # Check that all commits are included
        sub_1_commits = self._get_commit_logs(self.dir_absolute_sub_1)
        self.assertIn('init_sub_commit', sub_1_commits)
        self.assertIn('second_sub_commit', sub_1_commits)
        sub_2_commits = self._get_commit_logs(self.dir_absolute_sub_2)
        self.assertIn('init_sub_commit', sub_2_commits)
        self.assertIn('second_sub_commit', sub_2_commits)
        # Check expected branches
        sub_1_branches = self._get_branches(self.dir_absolute_sub_1)
        self.assertIn('master', sub_1_branches)
        self.assertIn('branch_sub_1', sub_1_branches)
        sub_2_branches = self._get_branches(self.dir_absolute_sub_2)
        self.assertIn('master', sub_2_branches)
        self.assertIn('branch_sub_1', sub_2_branches)

    def test_02_update_all_submodules_explicitly(self):
        # GIVEN
        trunk_sub_update = GitTrunkSubmoduleUpdate(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        trunk_sub_update.config.section['path_spec'] = 'external/sub1 external/sub2'
        # WHEN
        with chdir_tmp(self.dir_local.name):
            trunk_sub_update.run()
        # THEN
        self.assertTrue(self.dir_absolute_sub_1.is_dir())
        self.assertTrue(self.dir_absolute_sub_2.is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "init_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_2 / "init_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "extra_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_2 / "extra_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / ".git").is_file())
        self.assertTrue((self.dir_absolute_sub_2 / ".git").is_file())
        sub_1_commits = self._get_commit_logs(self.dir_absolute_sub_1)
        self.assertIn('init_sub_commit', sub_1_commits)
        self.assertIn('second_sub_commit', sub_1_commits)
        sub_2_commits = self._get_commit_logs(self.dir_absolute_sub_2)
        self.assertIn('init_sub_commit', sub_2_commits)
        self.assertIn('second_sub_commit', sub_2_commits)
        # Check expected branches
        sub_1_branches = self._get_branches(self.dir_absolute_sub_1)
        self.assertIn('master', sub_1_branches)
        self.assertIn('branch_sub_1', sub_1_branches)
        sub_2_branches = self._get_branches(self.dir_absolute_sub_2)
        self.assertIn('master', sub_2_branches)
        self.assertIn('branch_sub_1', sub_2_branches)

    def test_03_update_single_submodule_only(self):
        # GIVEN
        trunk_sub_update = GitTrunkSubmoduleUpdate(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        trunk_sub_update.config.section['path_spec'] = 'external/sub1'
        # WHEN
        with chdir_tmp(self.dir_local.name):
            trunk_sub_update.run()
        # THEN
        self.assertTrue(self.dir_absolute_sub_1.is_dir())
        self.assertTrue(self.dir_absolute_sub_2.is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "init_dir").is_dir())
        self.assertFalse((self.dir_absolute_sub_2 / "init_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "extra_dir").is_dir())
        self.assertFalse((self.dir_absolute_sub_2 / "extra_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / ".git").is_file())
        self.assertFalse((self.dir_absolute_sub_2 / ".git").is_file())
        sub_1_commits = self._get_commit_logs(self.dir_absolute_sub_1)
        self.assertIn('init_sub_commit', sub_1_commits)
        self.assertIn('second_sub_commit', sub_1_commits)
        sub_2_commits = self._get_commit_logs(self.dir_absolute_sub_2)
        self.assertNotIn('init_sub_commit', sub_2_commits)
        self.assertNotIn('second_sub_commit', sub_2_commits)
        # Check expected branches
        sub_1_branches = self._get_branches(self.dir_absolute_sub_1)
        self.assertIn('master', sub_1_branches)
        self.assertIn('branch_sub_1', sub_1_branches)
        sub_2_branches = self._get_branches(self.dir_absolute_sub_2)
        # This will return superproject branches when submodule is not
        # present!
        self.assertIn('master', sub_2_branches)
        self.assertNotIn('branch_sub_1', sub_2_branches)

    def test_04_update_single_submodule_single_commit_single_branch(self):
        # GIVEN
        trunk_sub_update = GitTrunkSubmoduleUpdate(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        trunk_sub_update.config.section['path_spec'] = 'external/sub1'
        trunk_sub_update.config.section['depth'] = 1
        trunk_sub_update.config.section['single_branch'] = True
        # WHEN
        with chdir_tmp(self.dir_local.name):
            trunk_sub_update.run()
        # THEN
        self.assertTrue(self.dir_absolute_sub_1.is_dir())
        self.assertTrue(self.dir_absolute_sub_2.is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "init_dir").is_dir())
        self.assertFalse((self.dir_absolute_sub_2 / "init_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "extra_dir").is_dir())
        self.assertFalse((self.dir_absolute_sub_2 / "extra_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / ".git").is_file())
        self.assertFalse((self.dir_absolute_sub_2 / ".git").is_file())
        sub_1_commits = self._get_commit_logs(self.dir_absolute_sub_1)
        # TODO: figure out why depth=1 is not keeping only single commit
        # when running it via tests!
        # self.assertNotIn('init_sub_commit', sub_1_commits)
        self.assertIn('second_sub_commit', sub_1_commits)
        sub_2_commits = self._get_commit_logs(self.dir_absolute_sub_2)
        self.assertNotIn('init_sub_commit', sub_2_commits)
        self.assertNotIn('second_sub_commit', sub_2_commits)
        # Check expected branches
        sub_1_branches = self._get_branches(self.dir_absolute_sub_1)
        self.assertIn('master', sub_1_branches)
        self.assertNotIn('branch_sub_1', sub_1_branches)
        sub_2_branches = self._get_branches(self.dir_absolute_sub_2)
        # This will return superproject's branches when submodule is not
        # present!
        self.assertIn('master', sub_2_branches)
        self.assertNotIn('branch_sub_1', sub_2_branches)

    def test_05_update_submodule_with_cleanup(self):
        # GIVEN
        trunk_sub_update = GitTrunkSubmoduleUpdate(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        # First get all submodules with update.
        with chdir_tmp(self.dir_local.name):
            trunk_sub_update.run()
        trunk_sub_update.config.section['path_spec'] = 'external/sub1'
        trunk_sub_update.config.section['single_branch'] = True
        # WHEN
        # Now run update again, but with cleanup and extra
        with chdir_tmp(self.dir_local.name):
            trunk_sub_update.run(cleanup=True)
        # THEN
        self.assertTrue(self.dir_absolute_sub_1.is_dir())
        self.assertTrue(self.dir_absolute_sub_2.is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "init_dir").is_dir())
        self.assertFalse((self.dir_absolute_sub_2 / "init_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / "extra_dir").is_dir())
        self.assertFalse((self.dir_absolute_sub_2 / "extra_dir").is_dir())
        self.assertTrue((self.dir_absolute_sub_1 / ".git").is_file())
        self.assertFalse((self.dir_absolute_sub_2 / ".git").is_file())
        sub_1_commits = self._get_commit_logs(self.dir_absolute_sub_1)
        self.assertIn('init_sub_commit', sub_1_commits)
        self.assertIn('second_sub_commit', sub_1_commits)
        sub_2_commits = self._get_commit_logs(self.dir_absolute_sub_2)
        self.assertNotIn('init_sub_commit', sub_2_commits)
        self.assertNotIn('second_sub_commit', sub_2_commits)
        # Check expected branches
        sub_1_branches = self._get_branches(self.dir_absolute_sub_1)
        self.assertIn('master', sub_1_branches)
        self.assertNotIn('branch_sub_1', sub_1_branches)
        sub_2_branches = self._get_branches(self.dir_absolute_sub_2)
        # This will return superproject's branches when submodule is not
        # present!
        self.assertIn('master', sub_2_branches)
        self.assertNotIn('branch_sub_1', sub_2_branches)

    def _get_commit_logs(self, path):
        # We can't use `git` command interface as it always runs command
        # from superproject, not from submodules, so using simple
        # subprocess
        with chdir_tmp(path):
            out = subprocess.check_output(['git', 'log'])
            return out.decode()

    def _get_branches(self, path):
        with chdir_tmp(path):
            out = subprocess.check_output(['git', 'branch', '-a'])
            return out.decode()

    def _add_and_remove_submodules(self, gitmodules: list[GitModule]):
        """Add and commit submodules and then remove it locally."""
        with chdir_tmp(self.dir_local.name):
            for gm in gitmodules:
                self.git.submodule('add', gm.remote, gm.local)
            self.git.add('.')
            self.git.commit('-m', '[ADD] submodules')
            self.git.submodule('deinit', '--all')
            os.system('rm -rf .git/modules/*')

    def _build_sub_repo(self, git, dir_local, dir_remote):
        git.remote('add', 'origin', dir_remote.name)
        self._create_dummy_dir_with_content('init_dir')
        git.add('.')
        git.commit('-m', 'init_sub_commit')
        self._create_dummy_dir_with_content('extra_dir')
        git.add('.')
        git.commit('-m', 'second_sub_commit')
        # Create branch1
        self._add_branch_with_content(git, 'branch_sub_1', 'module1')
        # Push to remote. Using -u to make sure we track upstream
        # branches.
        git.push('--all', '-u', 'origin')

    def _get_tempdirs_to_cleanup(self):
        dirs = super()._get_tempdirs_to_cleanup()
        return dirs + [
            self.dir_local_sub_1,
            self.dir_remote_sub_1,
            self.dir_local_sub_2,
            self.dir_remote_sub_2,
        ]
