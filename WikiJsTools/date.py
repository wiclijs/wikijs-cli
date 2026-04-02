####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['date2str']

####################################################################################################

from datetime import datetime

from dateutil import tz

####################################################################################################

UTC_ZONE = tz.tzutc()
LOCAL_ZONE = tz.tzlocal()

####################################################################################################

def date2str(date: datetime, local: bool = True) -> str:
    _ = date.astimezone(LOCAL_ZONE if local else UTC_ZONE)
    return _.strftime('%Y/%m/%d %H:%M:%S')
