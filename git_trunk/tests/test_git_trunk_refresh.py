from git_trunk.git_trunk import GitTrunkRefresh
from . import common


class TestGitTrunkRefresh(common.GitTrunkCommon):
    """Class to test git-trunk refresh command."""

    def setUp(self):
        """Add extra commit for master on remote."""
        super().setUp()
        self._create_dummy_commit('master_dir')
        self.git.push()
        self.git.reset('--hard', 'HEAD~1')

    def _test_git_refresh(self, active, remote=False, diff=None):
        if remote:
            last_target_commit = self.git.ls_remote(
                '--heads', 'origin', 'master').split()[0]
            trunk_branch_name = 'origin/master'

        else:
            trunk_branch_name = 'master'
            last_target_commit = self.git.show_ref(
                '--heads', '-s', trunk_branch_name)
        last_common_commit = self.git.merge_base(
            active, trunk_branch_name)
        # Checking if active branch is up to date on trunk branch.
        self.assertEqual(last_target_commit, last_common_commit)
        # Check if active branch is the same were refresh started.
        self.assertEqual(
            self.git_trunk_init.repo.active_branch.name, active)
        if diff is not None:
            self.assertEqual(self.git.diff(), diff)

    def test_01_git_refresh(self):
        """Refresh trunk branch when checked out trunk branch.

        Case 1: remote is 1 commit behind.
        Case 2: local and remote are the same.
        """
        # Case 1.
        trunk_refresh = GitTrunkRefresh(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        trunk_refresh.run()
        self._test_git_refresh('master', remote=True)
        # Case 2.
        trunk_refresh.run()
        self._test_git_refresh('master', remote=True)

    def test_02_git_refresh(self):
        """Refresh trunk branch when checked out other branch.

        Case 1: active behind trunk.
        Case 2: active behind trunk and has uncommitted changes.
        Case 3: active up to date with trunk. With Uncommitted changes.
        Case 4: active up to date with trunk. No uncommitted changes.
        """
        # Case 1.
        self.git.checkout('branch1')
        trunk_refresh = GitTrunkRefresh(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        trunk_refresh.run()
        self._test_git_refresh('branch1', diff='')
        # Case 2.
        self._update_dummy_file_in_dir('module1')
        diff = self.git.diff()
        trunk_refresh.run()
        self._test_git_refresh('branch1', diff=diff)
        trunk_refresh.run()
        # Case 3.
        # Run again when already refreshed.
        self._test_git_refresh('branch1', diff=diff)
        # Case 4.
        self.git.add('.')
        self.git.commit('-m', 'new commit blabla')
        self._test_git_refresh('branch1', diff='')

    def test_03_git_refresh(self):
        """Refresh trunk branch when having changes on submodule."""
        self._create_dummy_submodule('init_submodule_dir')
        self._update_dummy_file_in_dir('init_submodule_dir')
        trunk_refresh = GitTrunkRefresh(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        diff = self.git.diff()
        trunk_refresh.run()
        self._test_git_refresh('master', diff=diff)
