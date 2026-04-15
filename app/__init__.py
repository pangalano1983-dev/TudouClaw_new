# Tudou Claws AI Programming Assistant
__version__ = "0.1.0"

# Default runtime data directory — ONE ROOT for everything.
# Override with --data-dir CLI flag or TUDOU_CLAW_DATA_DIR env var.
#
# Directory layout under this root:
#   ~/.tudou_claw/
#   ├── workspaces/
#   │   ├── agents/{agent_id}/        ← each agent's private workspace
#   │   │   ├── workspace/            ← working files, Scheduled.md, Tasks.md
#   │   │   ├── session/
#   │   │   ├── memory/
#   │   │   └── logs/
#   │   └── shared/{project_id}/      ← project shared workspace (all members see)
#   ├── agents.json                   ← agent persistence
#   ├── projects.json                 ← project persistence
#   ├── skills/                       ← global skill files
#   ├── experience/                   ← experience library data
#   └── ...
import os as _os

USER_HOME = _os.path.expanduser("~")
DEFAULT_DATA_DIR = _os.path.join(USER_HOME, ".tudou_claw")
