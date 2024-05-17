from importlib.metadata import version, PackageNotFoundError
try:
    __version__ = version("git_trunk")
except PackageNotFoundError:
    __version__ = 'unknown'
