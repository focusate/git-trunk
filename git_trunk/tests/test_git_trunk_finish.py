from footil.path import chdir_tmp
from git_trunk import git_trunk
from git_trunk.git_trunk import GitTrunkFinish
from git.exc import GitCommandError
from . import common


class TestGitTrunkFinish(common.GitTrunkCommon):
    """Class to test git-trunk finish command."""

    def _test_finish(
        self,
        source,
        target,
        commits_count,
            check_trunk_branch_remote=True):
        count = self.git.rev_list('--count', target)
        self.assertEqual(int(count), commits_count)
        # Source must not exist both locally and remotely (feature
        # branch)
        # Check if source branch exists locally.
        try:
            self.git.show_ref('--verify', 'refs/heads/%s' % source)
        except GitCommandError as e:
            # Non zero code means, branch can't be found.
            self.assertNotEqual(e.status, 0)
        # Check if source branch exists remotely.
        try:
            self.git.ls_remote('--exit-code', '--heads', 'origin', source)
        except GitCommandError as e:
            self.assertNotEqual(e.status, 0)
        # Trunk branch check.
        try:
            self.git.show_ref('--verify', 'refs/heads/%s' % target)
        except GitCommandError:
            self.fail("Trunk branch must exist locally.")
        if check_trunk_branch_remote:
            try:
                self.git.ls_remote('--exit-code', '--heads', 'origin', target)
            except GitCommandError:
                self.fail("Trunk branch must exist remotely.")

    def test_01_git_finish(self):
        """Remove trunkbranch option from section."""
        with self.git_trunk_init.repo.config_writer() as cw:
            cw.remove_option(
                git_trunk.BASE_SECTION, 'trunkbranch')
        with self.assertRaises(ValueError):
            GitTrunkFinish(repo_path=self.dir_local.name).run()

    def test_02_git_finish(self):
        """Remove trunk section from git config."""
        with self.git_trunk_init.repo.config_writer() as cw:
            cw.remove_section(
                git_trunk.BASE_SECTION)
        with self.assertRaises(ValueError):
            GitTrunkFinish(repo_path=self.dir_local.name).run()

    def test_03_git_finish(self):
        """Finish branch1 with upstream."""
        with chdir_tmp(self.dir_local.name):
            self.git.checkout('branch1')
            GitTrunkFinish(log_level=common.LOG_LEVEL).run()
            self._test_finish('branch1', 'master', 2)

    def test_04_git_finish(self):
        """Finish branch2 without upstream."""
        with chdir_tmp(self.dir_local.name):
            self.git.checkout('branch2')
            GitTrunkFinish(log_level=common.LOG_LEVEL).run()
            self._test_finish('branch2', 'master', 2)

    def test_05_git_finish(self):
        """Finish branch1 with --no-ff flag."""
        with chdir_tmp(self.dir_local.name):
            self.git.checkout('branch1')
            trunk_finish = GitTrunkFinish(log_level=common.LOG_LEVEL)
            trunk_finish.config.section['ff'] = False
            trunk_finish.run()
            # One extra commit is merge commit.
            self._test_finish('branch1', 'master', 3)

    def test_06_git_finish(self):
        """Finish branch1 with local remote branch removed."""
        with chdir_tmp(self.dir_local.name):
            self.git.checkout('branch1')
            self.git.branch('-dr', 'origin/branch1')
            GitTrunkFinish(log_level=common.LOG_LEVEL).run()
            self._test_finish('branch1', 'master', 2)

    def test_07_git_finish(self):
        """Try to finish trunk branch.

        Also try to finish with local trunk branch removed.
        """
        with chdir_tmp(self.dir_local.name):
            with self.assertRaises(ValueError):
                GitTrunkFinish(log_level=common.LOG_LEVEL).run()
            self.git.checkout('branch1')
            self.git.branch('-D', 'master')
            with self.assertRaises(ValueError):
                GitTrunkFinish(log_level=common.LOG_LEVEL).run()

    def test_08_git_finish(self):
        """Finish branch1 with remote removed."""
        with chdir_tmp(self.dir_local.name):
            self.git.checkout('branch1')
            self.git.remote('rm', 'origin')
            trunk_finish = GitTrunkFinish(log_level=common.LOG_LEVEL)
            trunk_finish.config.section['ff'] = False
            trunk_finish.run()
            # One extra commit is merge commit. 128, because remote
            # can't be found (we removed it).
            self._test_finish(
                'branch1', 'master', 3, check_trunk_branch_remote=False)

    def test_09_git_finish(self):
        """Try to Finish branch1 with extra commit on remote."""
        with chdir_tmp(self.dir_local.name):
            self.git.checkout('branch1')
            self._create_dummy_dir_with_content('new_dir123')
            self.git.add('.')
            self.git.commit('-m "[ADD] new_dir123"')
            self.git.push()
            # Remove last commit, so it would not be up to date with
            # remote.
            self.git.reset('--hard', 'HEAD~1')
            with self.assertRaises(ValueError):
                GitTrunkFinish(log_level=common.LOG_LEVEL).run()

    def test_10_git_finish(self):
        """Try to Finish branch when it is not ahead trunk."""
        with chdir_tmp(self.dir_local.name):
            self.git.checkout('-b', 'new_branch')
            with self.assertRaises(ValueError):
                GitTrunkFinish(log_level=common.LOG_LEVEL).run()

    def test_11_git_finish(self):
        """Finish branch when it has release prefix.

        Case 1: Default 'release/' prefix is used.
        Case 2: '' prefix is used (prefix is disabled).
        """
        trunk_latest_commit = self.git.rev_list('master', '-1')
        self.git.checkout('-b', 'release/1.0.0')
        self._create_dummy_commit('new_dir1')
        trunk_finish = GitTrunkFinish(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL
        )
        trunk_finish.run()
        # Make sure, Release branch was not merged on trunk.
        self.assertEqual(
            trunk_latest_commit, self.git.rev_list('master', '-1'))
        # Check if release branch was deleted.
        with self.assertRaises(GitCommandError):
            self.git.show_ref('--heads', 'release/1.0.0')
        trunk_finish.config.sections[git_trunk.RELEASE_SECTION][
            'branch_prefix'] = ''
        self.git.checkout('-b', '2.0.0')
        self._create_dummy_commit('new_dir2')
        active_latest_commit = self.git.rev_list('2.0.0', '-1')
        trunk_finish.run()
        # 2.0.0 is not considered release branch, so must be merged into
        # trunk.
        self.assertEqual(
            active_latest_commit, self.git.rev_list('master', '-1'))
        with self.assertRaises(GitCommandError):
            self.assertFalse(self.git.show_ref('--heads', '2.0.0'))
