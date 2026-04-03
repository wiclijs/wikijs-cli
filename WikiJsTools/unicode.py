####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['usorted', 'usorted_key']

####################################################################################################

from collections.abc import Iterable, KeysView
from typing import Any

# To sort correctly latin and unicode
import icu

# Fixme: https://github.com/python/typeshed
collator = icu.Collator.createInstance(icu.Locale('fr_FR'))  # ty:ignore[unresolved-attribute] / icu

####################################################################################################

# Note: for typing we split usorted in two variants

def usorted(iter: Iterable[str] | KeysView[str]) -> list:
    return sorted(iter, key=collator.getSortKey)

def usorted_key(iter: Iterable[Any], key: str) -> list:
    return sorted(iter, key=lambda _: collator.getSortKey(getattr(_, key)))
