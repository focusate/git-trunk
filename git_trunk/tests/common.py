import os
import tempfile
import unittest
import uuid
from footil.path import chdir_tmp
from git import Repo


from git_trunk.git_trunk import GitTrunkInit

DUMMY_FILE_NAME = 'dummy_file.txt'
DUMMY_FILE_CONTENT = 'abc'
LOG_LEVEL = 'ERROR'


def _write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)


class GitTrunkCommon(unittest.TestCase):
    """Common class for git_trunk tests."""

    def _build_repo(self, git, dir_local, dir_remote):
        git.remote('add', 'origin', dir_remote.name)
        self._create_dummy_dir_with_content('init_dir')
        git.add('.')
        git.commit('-m', 'init commit')
        # Create branch1
        git.checkout('-b', 'branch1')
        self._create_dummy_dir_with_content('module1')
        git.add('.')
        git.commit('-m', '[ADD] module1')
        # Get back to master.
        git.checkout('master')
        # Push to remote. Using -u to make sure we track upstream
        # branches.
        git.push('--all', '-u', 'origin')
        # Create branch2 (wont be saved on remote).
        git.checkout('-b', 'branch2')
        self._create_dummy_dir_with_content('module2')
        git.add('.')
        git.commit('-m', '[ADD] module2')
        # Get back to master.
        git.checkout('master')

    def _create_dummy_dir_with_content(self, dir_name):
        os.mkdir(dir_name)
        _write_file(
            os.path.join(dir_name, DUMMY_FILE_NAME), DUMMY_FILE_CONTENT)

    def _update_dummy_file_in_dir(self, dir_name):
        with chdir_tmp(self.dir_local.name):
            _write_file(
                os.path.join(dir_name, DUMMY_FILE_NAME), str(uuid.uuid1()))

    def _create_dummy_commit(self, dir_name, body=None):
        with chdir_tmp(self.dir_local.name):
            self._create_dummy_dir_with_content(dir_name)
        self.git.add('.')
        msg = '[ADD] %s' % dir_name
        if body:
            msg += '\n%s' % body
        self.git.commit('-m', msg)

    def _setup_repo(self, build):
        dir_remote = tempfile.TemporaryDirectory()
        # Remote.
        Repo.init(dir_remote.name, bare=True)
        dir_local = tempfile.TemporaryDirectory()
        # Initialize repo and get git command interface for it.
        git = Repo.init(dir_local.name).git()
        with chdir_tmp(dir_local.name):
            # When build is called, local and remote repos are already
            # initiated and active directory is at local dir.
            build(git, dir_local, dir_remote)
        return git, dir_local, dir_remote

    def setUp(self):
        """Set up dummy repository for testing."""
        super().setUpClass()
        self.git, self.dir_local, self.dir_remote = self._setup_repo(
            self._build_repo)
        self.git_trunk_init = GitTrunkInit(
            trunk_branch='master',
            repo_path=self.dir_local.name,
            log_level=LOG_LEVEL,
            edit_tag_message=False,  # to not pop up tag msg to edit
            edit_squash_message=False)
        self.git_trunk_init.run()

    def _teardown_repo(self, directory):
        directory.cleanup()

    def tearDown(self):
        """Tear down dummy repositories."""
        super().tearDown()
        self._teardown_repo(self.dir_local)
        self._teardown_repo(self.dir_remote)
