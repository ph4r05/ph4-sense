"""Make ph4ha/apps importable as a flat module path for these tests.

The blinds_policy module lives in ph4ha/apps/ which is an AppDaemon apps
directory, not a Python package — so we add it to sys.path here rather than
turn it into a package and risk confusing AppDaemon's loader.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APPS = os.path.normpath(os.path.join(_HERE, "..", "..", "ph4ha", "apps"))
if _APPS not in sys.path:
    sys.path.insert(0, _APPS)
