#! /usr/bin/env python3

####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['main']

####################################################################################################

import argparse

from WikiJsTools.Cli import Cli
from WikiJsTools.WikiJsApi import WikiJsApi
from WikiJsTools import config as Config
from WikiJsTools import logging as Logging

####################################################################################################

def main():
    parser = argparse.ArgumentParser(
        prog='wikijs-cli',
        description='A CLI for Wiki.js',
        epilog='',
    )
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    if args.debug:
        Config.DEBUG = True
    config = Config.load_config()
    logger = Logging.setup_logging(
        config_file=config.LOGGING_CONFIG_FILE,
        level='DEBUG' if args.debug else 'INFO',
    )
    logger.info("Start...")

    api = WikiJsApi(api_url=config.API_URL, api_key=config.API_KEY)

    cli = Cli(api)
    cli.cli(query='')
