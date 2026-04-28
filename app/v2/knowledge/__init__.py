"""Back-compat shim: re-export from ``app.knowledge``.

The wiki layer was relocated out of the V2 namespace because V2 itself
is deprecated; the wiki is forward-going infrastructure. Old imports
keep working via this re-export so we don't have to touch every call
site at once.
"""
from app.knowledge import (   # absolute import — `..knowledge` is self
    WikiStore, WikiPage, get_wiki_store, slugify, VALID_KINDS,
)

# Also re-export the wiki_store submodule so paths like
# ``app.v2.knowledge.wiki_store`` keep resolving.
import app.knowledge as _knowledge_pkg
import sys as _sys
_sys.modules[__name__ + ".wiki_store"] = _knowledge_pkg.wiki_store

__all__ = [
    "WikiStore", "WikiPage", "get_wiki_store",
    "slugify", "VALID_KINDS",
]
