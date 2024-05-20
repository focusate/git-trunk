from git_trunk.git_trunk_commands import GitTrunkInit
from git_trunk.git_trunk_config import (
    BASE_SECTION,
    START_SECTION,
    FINISH_SECTION,
    RELEASE_SECTION,
    SQUASH_SECTION,
    SUBMODULE_UPDATE_SECTION,
)
from . import common


class TestGitTrunkInit(common.GitTrunkCommon):
    """Class to test git-trunk init command."""

    def _test_init(self, trunk_init, path_section=None):
        to_git_section = trunk_init.config._to_git_section
        with trunk_init._config._config_reader() as cr:
            self.assertEqual(
                cr.get_value(
                    to_git_section(BASE_SECTION, path=path_section),
                    'trunkbranch'
                ),
                'master'
            )
            self.assertEqual(
                cr.get_value(
                    to_git_section(RELEASE_SECTION, path=path_section),
                    'versionprefix'
                ),
                ''
            )
            self.assertEqual(
                cr.get_value(
                    to_git_section(RELEASE_SECTION, path=path_section),
                    'usesemver'
                ),
                True
            )
            self.assertEqual(
                cr.get_value(
                    to_git_section(RELEASE_SECTION, path=path_section),
                    'edittagmessage'
                ),
                False
            )
            self.assertEqual(
                cr.get_value(
                    to_git_section(SQUASH_SECTION, path=path_section),
                    'editsquashmessage'
                ),
                False
            )

    def test_01_git_init(self):
        """Initialize same trunkbranch, then new one.

        Case 1: init config with some custom values.
        Case 2: init config with all default values.
        """
        # init method allows to overwrite trunkbranch any time.
        # Case 1.
        trunk_init = GitTrunkInit(
            trunk_branch='master',
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL,
            edit_tag_message=False,
            edit_squash_message=False)
        trunk_init.run()
        self._test_init(trunk_init)
        # Case 2.
        trunk_init = GitTrunkInit(
            trunk_branch='master',
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL)
        trunk_init.run()
        self._test_init(trunk_init)
        return trunk_init  # For override

    def test_02_get_config(self):
        """Get config options.

        Check if every option has expected type.
        """
        self.git_trunk_init._init_cfg[BASE_SECTION]['trunkbranch'] = '12.0'
        self.git_trunk_init._init_cfg[RELEASE_SECTION]['versionprefix'] = '1'
        self.git_trunk_init._init_cfg[SUBMODULE_UPDATE_SECTION]['pathspec'] = 'abc'
        self.git_trunk_init.run()
        trunk_init = GitTrunkInit(
            repo_path=self.dir_local.name, log_level=common.LOG_LEVEL)
        config = trunk_init.config
        self.assertEqual(
            config.sections,
            # Note. Other defaults are modified on common.py.
            {
                BASE_SECTION: {
                    'trunk_branch': '12.0',
                },
                START_SECTION: {
                    'fetch_branch_pattern': '*',
                },
                FINISH_SECTION: {
                    'ff': True,
                    'require_squash': False,
                },
                RELEASE_SECTION: {
                    'version_prefix': '1',
                    'release_branch_prefix': 'release/',
                    'use_semver': True,
                    'edit_tag_message': False,
                },
                SQUASH_SECTION: {
                    'edit_squash_message': False,
                    'force_push_squash': True
                },
                SUBMODULE_UPDATE_SECTION: {
                    'path_spec': 'abc',
                    'depth': 0,
                    'single_branch': False,
                },
            }
        )

    def test_03_remote_name(self):
        """Get remote name with set/not set active branch.

        Case 1: default remote on active branch.
        Case 2: renamed remote for active tracking branch.
        Case 3: removed upstream for active branch.
        Case 4: no upstream for both active and trunk branches.
        """
        # Case 1.
        self.git.checkout('branch1')
        trunk_init = GitTrunkInit(
            repo_path=self.dir_local.name,
            log_level=common.LOG_LEVEL)
        self.assertEqual(trunk_init.remote_name, 'origin')
        # Case 2.
        self.git.remote('add', 'origin2', self.dir_remote.name)
        self.git.push('-u', 'origin2', 'branch1')
        self.assertEqual(trunk_init.remote_name, 'origin2')
        # Case 3.
        self.git.branch('--unset-upstream')
        self.assertEqual(trunk_init.remote_name, 'origin')
        # Case 4.
        self.git.checkout('master')
        self.git.branch('--unset-upstream')
        self.git.checkout('branch1')
        self.assertEqual(trunk_init.remote_name, False)


class TestGitTrunkInitSubmodule(
        common.GitTrunkSubmoduleCommon, TestGitTrunkInit):
    """Class to test git-trunk init command on submodule."""

    def _test_init(self, trunk_init, path_section=None):
        path_section = common.PATH_SUBMODULE
        super()._test_init(trunk_init, path_section=path_section)

    def test_01_git_init(self):
        """Check if submodule path is passed as section path."""
        trunk_init = super().test_01_git_init()
        self.assertEqual(
            trunk_init._config.path_section, common.PATH_SUBMODULE)
