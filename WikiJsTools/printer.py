####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['html_escape', 'printc', 'default_print', 'pt_print', 'STYLE', 'remove_style', 'CommandError']

####################################################################################################

from enum import Enum

from prompt_toolkit import HTML, print_formatted_text
from prompt_toolkit.styles import Style

####################################################################################################

# \033[   [<PREFIX>];[<COLOR>];[<TEXT DECORATION>]   m

# Foreground : 0
# Bold : 1
# Background : 3
# Underscore : 4

# Basic 8 colors : 30..37
# Basic high contrast colors : 90..97
# xterm-256 colors : 0..255

# bold \e[1;30m
# underline \e[4;30m
# bg \e[40m
# high intensity \e[0;90m
# bold hi \e[1;90m
# bh hi \e[0;100m
# xterm-256 colors \033[38;5;${code}m

####################################################################################################

class Palette(Enum):
    # RESET = '\033[0m'
    RESET = '\033[39m'

    BLACK = '\033[0;30m'
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[0;37m'

####################################################################################################

STYLE = Style.from_dict({
    # User input (default text)
    # '': '#000000',
    '': '#ffffff',
    # Prompt
    'prompt': '#ff0000',
    # Output
    # 'red': '#ff0000',
    # 'green': '#00ff00',
    # 'blue': '#0000ff',
    'red': '#ed1414',
    'green': '#10cf15',
    'blue': '#1b99f3',
    'orange': '#f57300',
    'violet': '#9b58b5',
    'greenblue': '#19bb9c',
})

####################################################################################################

# def default_print(*args, **kwargs):
def default_print(message: str) -> None:
    patterns = [
        (f'<{_.lower()}>', Palette._member_map_[_].value)
        for _ in Palette._member_names_
        if _ not in ('RESET')
    ]
    close_patterns = []
    for i, _ in patterns:
        close_patterns.append((i.replace('<', '</'), Palette.RESET.value))
    patterns += close_patterns
    # print(patterns)
    for i, o in patterns:
        message = message.replace(i, o)
    print(message)

####################################################################################################

def pt_print(message: str) -> None:
    # if message:
    html_message = HTML(message)
    print_formatted_text(
        html_message,
        style=STYLE,
    )

####################################################################################################

def remove_style(message: str) -> str:
    new_message = ''
    in_style = False
    for c in message:
        if in_style:
            if c == '>':
                in_style = False  # Fixme: ty
        else:
            if c == '<':
                in_style = True
            else:
                new_message += c
    return new_message

####################################################################################################

# html_escape = html.escape

def html_escape(text: str) -> str:
    return str(text).replace('<', '&lt;').replace('>', '&gt;')

####################################################################################################

# atprint = default_print
printc = pt_print

####################################################################################################

class CommandError(NameError):
    pass
