"""
vps_manager.version
~~~~~~~~~~~~~~~~~~~

Single source of truth for application version metadata.
Decoupled to eliminate module initialization circular dependencies.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from typing import Final

__version__: Final[str] = "2.0.0"
__author__: Final[str] = "Elite Systems Architecture"
__license__: Final[str] = "MIT"
