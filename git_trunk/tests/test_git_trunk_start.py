from git.exc import GitCommandError

from git_trunk.git_trunk import GitTrunkStart
from . import common

BRANCH_NAMES = [
    'test1-yours',
    'test2-my',
    'test3-yours',
    'test4-my',
    'test5-my',
    'test6-yours',
]


class TestGitTrunkStart(common.GitTrunkCommon):
    """Class to test git-trunk start command."""

    def _create_branches(self, branch_names):
        for branch_name in branch_names:
            self.git.checkout('-b', branch_name)

    def _delete_branches(self, branch_names):
        for branch_name in branch_names:
            self.git.branch('-dr', 'origin/%s' % branch_name)
            try:
                self.git.branch('-d', branch_name)
            except GitCommandError:
                pass

    def setUp(self):
        """Set remote branches for testing."""
        super().setUp()
        # Adding test0-my so it would act as already used branch.
        self._create_branches(['test0-my'] + BRANCH_NAMES)
        # Add symbolic references to make sure it will be ignored.
        self.git.symbolic_ref(
            'refs/remotes/origin/AHEAD', 'refs/remotes/origin/master')
        self.git.symbolic_ref(
            'refs/heads/ANEW', 'refs/remotes/origin/master')
        # Push branches so those would be on remote (before being
        # deleted remotely).
        self.git.push('origin', '-u', '--all')
        self.git.checkout('master')
        self._delete_branches(BRANCH_NAMES)

    def _test_git_start(self, trunk_start, branch_name):
        self.assertEqual(trunk_start.active_branch_name, branch_name)
        self.assertFalse(trunk_start.count_commits_ahead_trunk())
        self.assertFalse(trunk_start.count_commits_behind_trunk())

    def test_01_git_start(self):
        """Try to create branch when rules do not allow it.

        Case 1: try to create existing branch.
        Case 2: try to create branch when not on trunk.
        Case 3: try to create branch when regex pattern cant find any
            branch.
        """
        # Case 1.
        trunk_start = GitTrunkStart(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL
        )
        with self.assertRaises(ValueError):
            trunk_start.run(name='branch1')
        with self.assertRaises(ValueError):
            trunk_start.run(name='master')
        # Case 2.
        self.git.checkout('branch1')
        with self.assertRaises(ValueError):
            trunk_start.run(name='new_branch')
        # Case 3.
        self.git.checkout('master')
        with self.assertRaises(ValueError):
            trunk_start.run(pattern='not_existing_branch_pattern')

    def test_02_git_start(self):
        """Create branches when rules allow it.

        Case 1: create branch by specifying custom name.
        Case 2: create first branch with all incl. pattern. No regex.
        Case 3: create first branch with all incl. pattern. Simple
            regex
        Case 4: create first branch with all incl. pattern. Advanced
            regex.
        Case 5. create first branch with *-my fetch pattern. No regex
            pattern.
        Case 6. create first branch with *-my fetch pattern. With regex.
        """
        # Case 1.
        trunk_start = GitTrunkStart(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL
        )
        trunk_start.run(name='branch3')
        self._test_git_start(trunk_start, 'branch3')
        # Case 2.
        self.git.checkout('master')
        trunk_start.run()
        self._test_git_start(trunk_start, 'test1-yours')
        self.git.checkout('master')
        trunk_start.run()
        self._test_git_start(trunk_start, 'test2-my')
        # Case 3.
        self.git.checkout('master')
        # Filter that means, branch name contains '4-'.
        trunk_start.run(pattern='4-')
        self._test_git_start(trunk_start, 'test4-my')
        # Case 4.
        self.git.checkout('master')
        # Branch name that does not end with -yours.
        trunk_start.run(pattern='.*(?<!-yours)$')
        # Without filter, it should be test3-yours, but filtering, next
        # one should be test5-my.
        self._test_git_start(trunk_start, 'test5-my')
        # Case 5.
        self.git.checkout('master')
        # Clear up started branches, so could be possible to fetch
        # with new fetch branch pattern.
        self._delete_branches(BRANCH_NAMES)
        trunk_start.config.section['fetch_branch_pattern'] = '*-my'
        trunk_start.run()
        self._test_git_start(trunk_start, 'test2-my')
        # Case 6.
        self.git.checkout('master')
        trunk_start.run(pattern='test5')
        self._test_git_start(trunk_start, 'test5-my')
