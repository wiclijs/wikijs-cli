####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['usorted']

####################################################################################################

# To sort correctly latin and unicode
import icu

# Fixme:
collator = icu.Collator.createInstance(icu.Locale('fr_FR'))  # ty:ignore[unresolved-attribute]

####################################################################################################

def usorted(iter: list, key: str | None = None) -> list:
    if key is not None:
        return sorted(iter, key=lambda _: collator.getSortKey(getattr(_, key)))
    else:
        return sorted(iter, key=collator.getSortKey)
