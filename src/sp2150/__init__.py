from importlib.metadata import PackageNotFoundError, version

# get version if package has been installed
try:
    __version__ = version("acton_sp2150")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .sp2150 import *
