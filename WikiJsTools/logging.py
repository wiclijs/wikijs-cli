####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

"""This subpackage implements logging facilities.

"""

####################################################################################################

__all__ = ['setup_logging']

####################################################################################################

import logging
import logging.config
import os
import sys
from pathlib import Path

import yaml

from WikiJsTools import config as Config

####################################################################################################

LEVEL_ENV = 'WikiJsCliLogLevel'

def setup_logging(
        application_name: str = 'WikiJsCli',
        config_file: Path | str = Config.DEFAULT_LOOGING_CONFIG_FILE,
        level: int | str | None = None,
) -> logging.Logger:

    # logging_config_file_name = config.Logging.find(config_file)
    _ = Path(config_file).read_text()
    logging_config = yaml.load(_, Loader=yaml.SafeLoader)

    # Fixme: \033 is not interpreted in YAML
    if Config.OS.on_linux:
        formatter_config = logging_config['formatters']['ansi']['format']
        logging_config['formatters']['ansi']['format'] = formatter_config.replace('<ESC>', '\033')

    # Use "simple" formatter for Windows and OSX
    # and "ansi" for Linux
    formatter = 'simple' if Config.OS.on_windows or Config.OS.on_osx else 'ansi'
    logging_config['handlers']['console']['formatter'] = formatter

    # Load YAML settings
    logging.config.dictConfig(logging_config)

    # Customise logging level
    logger = logging.getLogger(application_name)
    if level is None and LEVEL_ENV in os.environ:
        level_name = os.environ[LEVEL_ENV]
        try:
            level = getattr(logging, level_name.upper())
        except AttributeError:
            sys.exit(f'{LEVEL_ENV} environment variable is set to an invalid logging level "{level_name}"')
    if level:
        # level can be int or string
        logger.setLevel(level)
    # else use logging.yml

    return logger
