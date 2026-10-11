# SPDX-License-Identifier: Apache-2.0
"""The `resolve` and `clone` tools of mgtk-repo-utils (design sections 13 to 17).

Both read the `[clone]` table. `resolve` writes nothing; `clone` is the one tool
that writes outside the repository and uses the network.
"""

from __future__ import annotations

from mgtk_repo_utils.tool import Tool

from . import clone as _clone
from . import resolve as _resolve
from .config import TABLE, CloneConfig, SourceConfig
from .messages import MESSAGES

__all__ = ["CLONE", "RESOLVE", "CloneConfig", "SourceConfig", "TABLE"]

RESOLVE = Tool(
    name="resolve",
    table=TABLE,
    messages=MESSAGES,
    main=_resolve.main,
    check=lambda config: _resolve.run_check(config, "check"),
    check_order=40,
)
# Never a step of `check` (design section 11).
CLONE = Tool(name="clone", table=TABLE, messages=MESSAGES, main=_clone.main, check_order=50)
