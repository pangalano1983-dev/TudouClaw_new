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

# ── HuggingFace cache → project data dir, NOT ~/.cache ─────────────────
# Models like BAAI/bge-m3 are 2-3 GB each. Default HF cache lives in
# ~/.cache/huggingface/, which (a) pollutes the user's system cache and
# (b) makes per-deployment cleanup hard ("rm -rf ~/.tudou_claw" should
# wipe EVERYTHING this app produced). Pin both env vars BEFORE any
# transformers / sentence-transformers / huggingface-hub import so the
# library reads our value at first init.
#
# Override path via TUDOU_HF_CACHE if you want it on a different volume
# (large external SSD, shared cache for multiple deployments, etc).
# Falls back to TUDOU_CLAW_DATA_DIR override if set, else DEFAULT_DATA_DIR.
_HF_CACHE_DIR = (
    _os.environ.get("TUDOU_HF_CACHE")
    or _os.path.join(
        _os.environ.get("TUDOU_CLAW_DATA_DIR") or DEFAULT_DATA_DIR,
        "hf_cache",
    )
)
try:
    _os.makedirs(_HF_CACHE_DIR, exist_ok=True)
except OSError:
    pass
# HF_HOME is the umbrella var (newer); TRANSFORMERS_CACHE/HF_HUB_CACHE
# are the legacy ones some libs still read. Set all three so the cache
# location is unambiguous regardless of which entry-point loads first.
_os.environ.setdefault("HF_HOME", _HF_CACHE_DIR)
_os.environ.setdefault("HF_HUB_CACHE", _os.path.join(_HF_CACHE_DIR, "hub"))
_os.environ.setdefault("TRANSFORMERS_CACHE", _os.path.join(_HF_CACHE_DIR, "hub"))
_os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", _HF_CACHE_DIR)

# ── Suppress tqdm progress bars globally (Nov 2026) ────────────────────
# chromadb → sentence-transformers → .encode(show_progress_bar=True) by
# default, which floods logs with
#   Batches: 100%|████| 1/1 [00:00<00:00, 89.93it/s]
# one line per embedding batch. Users reported it drowns real signal.
#
# Defense in depth — TWO layers, both cheap, because either alone has
# escape hatches:
#
#   1. monkey-patch tqdm.__init__(default disable=True). Catches anyone
#      that lets disable default. Loses to callers that pass
#      `disable=False` explicitly — sentence-transformers IS one, since
#      it does `trange(..., disable=not show_progress_bar)`.
#
#   2. force sentence-transformers' logger level to WARNING. Its
#      `encode()` default is "show progress iff our logger is INFO/DEBUG"
#      (sentence_transformers/SentenceTransformer.py: encode()), so
#      WARNING+ silences it without touching tqdm.
#
# Escape hatch: TUDOU_TQDM=1 keeps everything alive (debugging).
if _os.environ.get("TUDOU_TQDM", "0") != "1":
    try:
        from functools import partialmethod as _pm
        # tqdm has MULTIPLE concrete classes and `tqdm.auto.tqdm` is usually
        # a DIFFERENT object from `tqdm.tqdm` (it picks notebook/asyncio/std
        # at import time). sentence-transformers does
        # `from tqdm.autonotebook import trange` → hits auto, bypasses std.
        # So we patch every known tqdm class.
        import tqdm as _tqdm
        import tqdm.std as _tqdm_std   # noqa
        import tqdm.auto as _tqdm_auto  # noqa
        import tqdm.autonotebook as _tqdm_ann  # noqa
        import tqdm.asyncio as _tqdm_ai  # noqa
        _candidates = []
        for _mod, _attr in [
            (_tqdm, "tqdm"), (_tqdm_std, "tqdm"),
            (_tqdm_auto, "tqdm"), (_tqdm_ann, "tqdm"),
            (_tqdm_ai, "tqdm_asyncio"),
        ]:
            _c = getattr(_mod, _attr, None)
            if _c is not None and _c not in _candidates:
                _candidates.append(_c)
        for _cls in _candidates:
            try:
                _cls.__init__ = _pm(_cls.__init__, disable=True)
            except Exception:
                pass
    except Exception:
        pass
    # Layer 2 — sentence-transformers checks ITS OWN logger level for the
    # show_progress_bar default. WARNING silences the default; we don't
    # touch its other log lines (model load info etc. — those stay).
    try:
        import logging as _logging
        _logging.getLogger("sentence_transformers").setLevel(_logging.WARNING)
        # Also the parent `sentence_transformers.SentenceTransformer`
        # logger that the encode() method uses.
        _logging.getLogger(
            "sentence_transformers.SentenceTransformer"
        ).setLevel(_logging.WARNING)
    except Exception:
        pass
