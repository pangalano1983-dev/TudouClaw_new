"""Legacy module path — real code in app/mcp/builtins/agentmail.py.

This shim keeps ``python -m app.tudou_agentmail_mcp`` working.
"""
from app.mcp.builtins.agentmail import *  # noqa: F401,F403
from app.mcp.builtins.agentmail import main  # noqa: F401


if __name__ == "__main__":
    main()
