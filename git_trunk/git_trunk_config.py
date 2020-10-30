"""Git Trunk configuration module.

Allows to save and retrieve trunk commands configuration via git config
file.
"""
from typing import Any, Optional, Union
import string
from configparser import NoSectionError, NoOptionError
import git  # GitPython

SEP = '"'
BASE_SECTION = 'trunk'
START_SECTION = 'start'
FINISH_SECTION = 'finish'
RELEASE_SECTION = 'release'
SQUASH_SECTION = 'squash'
SECTION_PATTERN = '{section} {sep}%s{sep}'.format(
    section=BASE_SECTION, sep=SEP)

# True means, BASE section, False other sections.
PATH_SECTION_PATTERN_MAP = {
    True: '{section} %(sep)s{path}%(sep)s' % {'sep': SEP},
    False: '{path}.{section}'
}
DEFAULT_FETCH_PATTERN = '*'


class GitTrunkConfig:
    """Class to manage git-trunk configuration."""

    @staticmethod
    def _to_git_section(section: str, path: Optional[str] = None) -> str:
        is_base = section == BASE_SECTION
        if path:
            path_section_pattern = PATH_SECTION_PATTERN_MAP[is_base]
            section = path_section_pattern.format(section=section, path=path)
        if is_base:
            return section
        return SECTION_PATTERN % section

    @classmethod
    def get_option_vals(
        self,
        name,
        default,
        forced_type=None,
        label=None,
            description='') -> dict:
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
    def get_config_struct(cls) -> dict:
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
                'requiresquash': cls.get_option_vals(
                    'require_squash',
                    default=False,
                    label="Finish Requires Squash",
                    description="Whether to require squash before finishing."
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

    def _get_config_template(self) -> dict:
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
                    git_section = self._to_git_section(
                        section, path=self.path_section)
                    cfg[section][vals['name']] = self.get_value(
                        cr, git_section, option, vals)
        return cfg

    def write(self, config: dict) -> None:
        """Write specified config on git config file."""
        with self._config_writer() as cw:
            for section, section_cfg in config.items():
                for option, val in section_cfg.items():
                    git_section = self._to_git_section(
                        section, path=self.path_section)
                    cw.set_value(git_section, option, val)

    def check_config(self, cfg: dict) -> bool:
        """Check if got configuration is correct one.

        Override to implement specific checks.
        """
        return True

    def __init__(
        self,
        config_reader: git.Repo.config_reader,
        config_writer: git.Repo.config_writer,
        section,
            path_section=None) -> None:
        """Initialize git trunk configuration."""
        super().__init__()
        self._config_reader = config_reader
        self._config_writer = config_writer
        self._section = section
        self._path_section = path_section
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
    def path_section(self) -> Union[str, None]:
        """Return section path."""
        return self._path_section

    @property
    def base(self) -> dict:
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
