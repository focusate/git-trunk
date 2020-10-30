import os
import tempfile
import unittest
import uuid
from footil.path import chdir_tmp
from git import Repo


from git_trunk.git_trunk_commands import GitTrunkInit

DUMMY_FILE_NAME = 'dummy_file.txt'
DUMMY_FILE_CONTENT = 'abc'
LOG_LEVEL = 'ERROR'
PATH_SUBMODULE = 'external/submodule'


def _write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)


class MockedPath:
    """Class to mimic tempfile object path."""

    def __init__(self, *paths):
        """Store path on name attribute, same as tempfile."""
        self.name = os.path.join(*paths)


class GitTrunkCommon(unittest.TestCase):
    """Common class for git_trunk tests."""

    def _add_branch_with_content(self, git, branch, name):
        git.checkout('-b', branch)
        self._create_dummy_dir_with_content(name)
        git.add('.')
        git.commit('-m', '[ADD] %s' % name)
        git.checkout('master')

    def _build_repo_simple(self, git, dir_local, dir_remote):
        git.remote('add', 'origin', dir_remote.name)
        self._create_dummy_dir_with_content('init_dir')
        git.add('.')
        git.commit('-m', 'init commit')
        git.push('--all', '-u', 'origin')

    def _build_repo(self, git, dir_local, dir_remote):
        git.remote('add', 'origin', dir_remote.name)
        self._create_dummy_dir_with_content('init_dir')
        git.add('.')
        git.commit('-m', 'init commit')
        # Create branch1
        self._add_branch_with_content(git, 'branch1', 'module1')
        # Push to remote. Using -u to make sure we track upstream
        # branches.
        git.push('--all', '-u', 'origin')
        # Create branch2 (wont be saved on remote).
        self._add_branch_with_content(git, 'branch2', 'module2')

    def _add_submodule(self, git, dir_remote_sub, path):
        git.submodule('add', dir_remote_sub, path)
        git.commit('-m', '[ADD] Submodule')

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

    def _setup_trunk_init(self):
        self.git_trunk_init = GitTrunkInit(
            trunk_branch='master',
            repo_path=self.dir_local.name,
            log_level=LOG_LEVEL,
            edit_tag_message=False,  # to not pop up tag msg to edit
            edit_squash_message=False)
        self.git_trunk_init.run()

    def _setup_trunk(self):
        self.git, self.dir_local, self.dir_remote = self._setup_repo(
            self._build_repo)
        self._setup_trunk_init()

    def setUp(self):
        """Set up dummy repository for testing."""
        super().setUpClass()
        self._setup_trunk()

    def _get_tempdirs_to_cleanup(self):
        return [
            self.dir_local,
            self.dir_remote
        ]

    def tearDown(self):
        """Tear down dummy repositories."""
        super().tearDown()
        [d.cleanup() for d in self._get_tempdirs_to_cleanup()]


class GitTrunkSubmoduleCommon(GitTrunkCommon):
    """Common class for git_trunk submodule tests."""

    def _setup_trunk(self):
        """Override to combine main repository with submodule one."""
        # Repo that will be added as submodule.
        # NOTE. submodule dir_local will be used as combination from
        # main repo and submodule path inside it.
        _, self.dir_local_sub, self.dir_remote = self._setup_repo(
            self._build_repo)
        # Repo that will be used as submodule holder.
        self.git_main, self.dir_local_main, self.dir_remote_main = (
            self._setup_repo(self._build_repo_simple))
        # Path used inside main repo when adding submodule.
        self._add_submodule(
            self.git_main, self.dir_remote.name, PATH_SUBMODULE)
        # Set variables as it would look like normal repo used from
        # GitTrunkCommon.
        self.dir_local = MockedPath(self.dir_local_main.name, PATH_SUBMODULE)
        repo_sub = Repo(self.dir_local.name)
        self.git = repo_sub.git()
        # Make submodule look like main repo.
        self.git.fetch('origin')
        self.git.checkout('branch1')
        self.git.checkout('master')
        # Re-add branch2 locally, because it is not on remote (so won't
        # be pulled).
        with chdir_tmp(self.dir_local.name):
            self._add_branch_with_content(self.git, 'branch2', 'module2')
        self._setup_trunk_init()

    def _get_tempdirs_to_cleanup(self):
        return [
            self.dir_remote,
            self.dir_local_sub,
            self.dir_local_main,
            self.dir_remote_main

        ]
