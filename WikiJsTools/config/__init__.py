####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = [
    'CONFIG_PATH',
    'CONFIG_YAML_PATH',
    'CLI_HISTORY_PATH',
    'load_config', 
]

####################################################################################################

from dataclasses import dataclass
from pathlib import Path

import yaml

from .os import OsFactory

####################################################################################################

CONFIG_PATH = Path('~/.config/wikijs-cli').expanduser()
CONFIG_YAML_PATH = CONFIG_PATH.joinpath('config.yaml')
CLI_HISTORY_PATH = CONFIG_PATH.joinpath('cli_history')

# DEBUG = True
DEBUG = False

OS = OsFactory()

DEFAULT_LOOGING_CONFIG_FILE =  Path(__file__).parent.joinpath('logging.yml')

####################################################################################################

@dataclass
class Config:
    API_URL: str
    API_KEY: str
    LOGGING_CONFIG_FILE: str = DEFAULT_LOOGING_CONFIG_FILE

####################################################################################################

def load_config(path: Path | str = CONFIG_YAML_PATH) -> Config:
    _ = Path(path).read_text()
    _ = yaml.load(_, Loader=yaml.SafeLoader)
    return Config(**_)
