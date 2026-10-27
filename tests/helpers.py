# -*- coding: utf-8 -*-
"""Shared test utilities and fixtures."""
import contextlib
import os
import sys
from unittest import mock

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PROJECT_PREFIXES = ("core.", "ui.", "platforms.", "features.")


def _project_modules():
    """Yield every loaded project module (core, ui, platforms, features, entry point)."""
    for mod_name, mod in list(sys.modules.items()):
        if mod is not None and (mod_name.startswith(PROJECT_PREFIXES) or mod_name == "haustus"):
            yield mod


def swap_config_mgr(new_cfg):
    """Point every project module's config_mgr at new_cfg. Returns the originals for restore_config_mgr()."""
    saved = {}
    for mod in _project_modules():
        if "config_mgr" in vars(mod):
            saved[mod.__name__] = mod.config_mgr
            mod.config_mgr = new_cfg
    return saved


def restore_config_mgr(saved):
    """Undo swap_config_mgr()."""
    for mod_name, cfg in saved.items():
        sys.modules[mod_name].config_mgr = cfg


@contextlib.contextmanager
def patch_everywhere(name, **mock_kwargs):
    """Replace `name` with one MagicMock in every project module that imported the same object."""
    holders = [mod for mod in _project_modules() if name in vars(mod)]
    if not holders:
        raise AttributeError(f"No loaded project module binds {name!r}")
    original = getattr(holders[0], name)
    fake = mock.MagicMock(**mock_kwargs)
    with contextlib.ExitStack() as stack:
        for mod in holders:
            if vars(mod).get(name) is original:
                stack.enter_context(mock.patch.object(mod, name, fake))
        yield fake
