from git_trunk.git_trunk import GitTrunkSquash
from . import common


class TestGitTrunkSquash(common.GitTrunkCommon):
    """Class to test git-trunk squash command."""

    def setUp(self):
        """Add extra commits for branch1.

        Current branch is left to be branch1.
        """
        super().setUp()
        self.git.checkout('branch1')
        self._create_dummy_commit('new_dir_1')
        self._create_dummy_commit('new_dir_2', body='\nnew dir 2 content')
        self.git.push()

    def _test_git_squash(
        self,
        trunk_squash,
        commits_ahead=1,
        diff=None,
        log_msg=None,
            remote='origin',
            behind_ahead_remote=(0, 0)):
        active = trunk_squash.active_branch_name
        target = trunk_squash.config.base['trunk_branch']
        self.assertEqual(active, self.git_trunk_init.active_branch_name)
        output = self.git.rev_list(
            '--left-right', '--count', '%s..%s' % (target, active))
        counts = output.split('\t')
        left = int(counts[0])
        right = int(counts[1])
        self.assertEqual(left, 0)  # not behind target.
        # Number of commits ahead of target.
        self.assertEqual(right, commits_ahead)
        if diff is not None:
            actual_diff = self.git.diff('%s..%s' % (target, active), '--stat')
            self.assertEqual(diff, actual_diff)
        if log_msg is not None:
            actual_log_msg = self.git.log('-1', '--format=%B')
            self.assertEqual(log_msg, actual_log_msg)
        if remote is not None:
            remote_branch = '%s/%s' % (remote, active)
            self.assertFalse(
                self.git.diff('%s..%s' % (active, remote_branch)))
            behind_ahead = trunk_squash.count_commits_behind_ahead(
                remote_branch, active)
            self.assertEqual(behind_ahead, behind_ahead_remote)

    def test_01_git_squash(self):
        """Try to squash when squash is not allowed.

        Case 1: there are uncommitted changes.
        Case 2: active branch is trunk branch.
        Case 3. want to squash more commits than are ahead.
        Case 4. no more than 1 ahead commit to squash.
        """
        # Case 1.
        self._update_dummy_file_in_dir('new_dir_1')
        trunk_squash = GitTrunkSquash(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        with self.assertRaises(ValueError):
            trunk_squash.run()
        self.git.stash()
        # Case 2.
        self.git.checkout('master')
        with self.assertRaises(ValueError):
            trunk_squash.run()
        self.git.checkout('branch1')
        # Case 3.
        with self.assertRaises(ValueError):
            trunk_squash.run(count=10)
        with self.assertRaises(ValueError):
            trunk_squash.run(count=3)
        # Case 4.
        self.git.reset('--hard', 'HEAD~2')
        with self.assertRaises(ValueError):
            trunk_squash.run()

    def test_02_git_squash(self):
        """Squash N commits.

        Case 1: use default max count. include_squash_msg=True.
        Case 2: squash custom count of commits. include_squash_msg=False.
        Case 3: squash custom count of commits.
            include_squash_msg=True, custom_msg set, disable force push
            after squashing.
        """
        # Case 1.
        trunk_squash = GitTrunkSquash(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
        )
        active_branch_name = 'branch1'
        diff = trunk_squash.git_diff(
            trunk_squash.config.base['trunk_branch'],
            active_branch_name,
            '--stat')
        # Squashing 2 commits and including commit it is squashed into.
        # 2 + 1 = 3
        log_msg = trunk_squash._get_n_logs_body(3)
        trunk_squash.run()  # include_squash_msg = True
        self._test_git_squash(
            trunk_squash, diff=diff, log_msg=log_msg)
        # Case 2.
        self._create_dummy_commit('new_dir_3')
        self._create_dummy_commit('new_dir_4')
        self._create_dummy_commit('new_dir_5')
        self._create_dummy_commit('new_dir_6')
        diff = trunk_squash.git_diff(
            trunk_squash.config.base['trunk_branch'],
            active_branch_name,
            '--stat')
        # One commit is squashed without include_squash_msg flag. Meaning
        # it will use commit message all are commits are squashed into.
        log_msg = self.git.log('-1', '--skip=1', '--format=%B')
        trunk_squash.run(count=1, include_squash_msg=False)
        # commits_ahead = 5 - 1 = 4 (5 commits before squash and 1
        # squashed)
        self._test_git_squash(
            trunk_squash,
            commits_ahead=4,
            diff=diff,
            log_msg=log_msg
        )
        # Case 3.
        custom_msg = 'my custom commit message\n'
        # Using include_squash_msg to make sure it is ignored, because
        # custom_msg is passed.
        trunk_squash.config.section['force_push_squash'] = False
        trunk_squash.run(
            count=2, include_squash_msg=True, custom_msg=custom_msg
        )
        self._test_git_squash(
            trunk_squash,
            commits_ahead=2,
            diff=diff,
            log_msg=custom_msg,
            behind_ahead_remote=(0, 1)  # squash not pushed yet.
        )
