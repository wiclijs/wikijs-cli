####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['OsFactory']

####################################################################################################

import sys

####################################################################################################

class OsFactory:

    ##############################################

    def __init__(self) -> None:
        if sys.platform.startswith('linux'):
            self._name = 'linux'
        elif sys.platform.startswith('win'):
            self._name = 'windows'
        elif sys.platform.startswith('darwin'):
            self._name = 'osx'

    ##############################################

    @property
    def name(self) -> str:
        return self._name

    @property
    def on_linux(self) -> bool:
        return self._name == 'linux'

    @property
    def on_windows(self) -> bool:
        return self._name == 'windows'

    @property
    def on_osx(self) -> bool:
        return self._name == 'osx'
