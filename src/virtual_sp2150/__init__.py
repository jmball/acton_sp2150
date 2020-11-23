from setuptools_scm import get_version
from pkg_resources import get_distribution, DistributionNotFound

# get version if running from git folder
try:
    __version__ = get_version(root="..", relative_to=__file__)
except LookupError:
    __version__ = None

# get version if package has been installed
if __version__ is None:
    try:
        __version__ = get_distribution(__name__).version
    except DistributionNotFound:
        __version__ = "0.0.0"
        pass

from .virtual_sp2150 import *
