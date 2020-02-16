"""Module to manage version validation and bumping."""
import abc
from typing import Any, Iterable, Optional, Union
import semver
import natsort

BASE_SECTION = 'trunk'

EMPTY_VERSION = '0.0.0'  # default version when are no versions yet


class BaseVersion(abc.ABC):
    """Base class for version management."""

    def __init__(
        self,
        versions: Union[Iterable, callable],
            empty_version: Optional[str] = EMPTY_VERSION) -> None:
        """Initialize base version attributes."""
        self._versions = versions
        self._empty_version = empty_version

    @property
    def versions(self) -> Iterable:
        """Get versions."""
        return self._versions() if callable(self._versions) else self._versions

    @versions.setter
    def versions(self, value: Any):
        raise AttributeError("attribute 'versions' is readonly")

    @abc.abstractmethod
    def get_latest_version(self):
        """Return latest version from existing versions.

        Must be overridden to implement it.
        """
        ...

    def generate_version(self, **kwargs) -> Union[None, str]:
        """Generate new version.

        Override to implement version generation.
        """
        return None

    def check_version(self, version: str) -> bool:
        """Check if specified version is valid as new version.

        Can be overridden to implement additional checks.
        """
        if not version:
            raise ValueError("Version is missing")
        if version in self.versions:
            raise ValueError("%s version already exists" % version)
        return True

    def get_version(self, version: Optional['str'] = None, **kwargs) -> str:
        """Generate new version or use passed one.

        Version is then checked by calling `check_version` to make sure
        its valid.
        """
        if not version:
            version = self.generate_version(**kwargs)
        self.check_version(version)
        return version


class GenericVersion(BaseVersion):
    """Generic versions management class."""

    def get_latest_version(self):
        """Find latest version using natural sorting."""
        try:
            return natsort.natsorted(self.versions, reverse=True)[0]
        except IndexError:
            return self._empty_version


class SemverVersion(BaseVersion):
    """Semver base versions management class."""

    def _get_semver_bump_methods_map(self):
        pattern = 'bump_%s'
        major = 'major'
        minor = 'minor'
        patch = 'patch'
        prerelease = 'prerelease'
        build = 'build'
        return {
            major: pattern % major,
            minor: pattern % minor,
            patch: pattern % patch,
            prerelease: pattern % prerelease,
            build: pattern % build,
            'final': 'finalize_version'
        }

    def get_latest_version(self):
        """Find latest version by finding max semver version."""
        max_ver = self._empty_version
        for version in self.versions:
            try:
                max_ver = semver.max_ver(max_ver, version)
            except ValueError:
                pass  # ignoring not semver valid versions.
        return max_ver

    def generate_version(self, part='minor') -> Union[None, str]:
        """Override to bump version part.

        Args:
            part: semver part to bump. Possible options:
                - 'major',
                - 'minor',
                - 'patch',
                - 'prerelease',
                - 'build'
                - 'final' - will remove prerelease/build parts.
        """
        bump_method_name = self._get_semver_bump_methods_map()[part]
        latest_ver = self.get_latest_version()
        return getattr(semver, bump_method_name)(latest_ver)

    def check_version(self, version: str) -> bool:
        """Override to check if version is semver valid."""
        result = super().check_version(version)
        semver.parse(version)
        return result
