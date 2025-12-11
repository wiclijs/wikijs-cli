####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

###################################################################################################

__all__ = ['Cli']

####################################################################################################

from pathlib import Path, PurePosixPath
from pprint import pprint
from typing import Iterable

# import logging
import difflib
import html
import inspect
import os
import re
import subprocess
import traceback

# See also [cmd — Support for line-oriented command interpreters — Python documentation](https://docs.python.org/3/library/cmd.html)
# Python Prompt Toolkit](https://python-prompt-toolkit.readthedocs.io/en/master/)
from prompt_toolkit import PromptSession, HTML
from prompt_toolkit import print_formatted_text, shortcuts
from prompt_toolkit.completion import WordCompleter, Completer, Completion, CompleteEvent
from prompt_toolkit.document import Document
# from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import ProgressBar

from .WikiJsApi import WikiJsApi, ApiError, Node, Page
from . import config
from . import sync
from .printer import STYLE, printc, CommandError
from .unicode import usorted

####################################################################################################

# _module_logger = logging.getLogger('')

LINESEP = os.linesep

# Fixme: ?
#  from typing import NewType
type CommandName = str
type PagePath = str   # aka PurePosixPath
type PageFolder = str   # aka PurePosixPath
type AssetFolder = str   # aka PurePosixPath
type FilePath = str   # aka Path
type Tag = str   # aka Path

####################################################################################################

class CustomCompleter(Completer):

    """
    Simple autocompletion on a list of words.

    :param words: List of words or callable that returns a list of words.
    :param ignore_case: If True, case-insensitive completion.
    :param meta_dict: Optional dict mapping words to their meta-text. (This
        should map strings to strings or formatted text.)
    :param WORD: When True, use WORD characters.
    :param sentence: When True, don't complete by comparing the word before the
        cursor, but by comparing all the text before the cursor. In this case,
        the list of words is just a list of strings, where each string can
        contain spaces. (Can not be used together with the WORD option.)
    :param match_middle: When True, match not only the start, but also in the
                         middle of the word.
    :param pattern: Optional compiled regex for finding the word before
        the cursor to complete. When given, use this regex pattern instead of
        default one (see document._FIND_WORD_RE)
    """

    ##############################################

    def __init__(self, cli, commands: list[str]) -> Node:
        self._cli = cli
        self._commands = commands

        self.ignore_case = True
        # self.display_dict = display_dict or {}
        # self.meta_dict = meta_dict or {}
        self.WORD = False
        self.sentence = False
        self.match_middle = False
        self.pattern = None

    ##############################################

    def _get_word_before_cursor1(self, document, separator: str) -> str:
        line = document.current_line
        index = line.rfind(separator)
        # "dump " -> ""
        # "dump /foo/b" -> "b"
        return line[index+1:]

    def _get_word_before_cursor2(self, document, separator: str) -> str:
        return document.text_before_cursor

    # cf. prompt_toolkit/completion/word_completer.py
    def _get_completions(
            self,
            document: Document,
            complete_event: CompleteEvent,
            words: list[str],
            separator: str,
            get_word_before_cursor,
    ) -> Iterable[Completion]:
        word_before_cursor = get_word_before_cursor(document, separator)

        def word_matches(word: str) -> bool:
            return word.startswith(word_before_cursor)

        for _ in words:
            if word_matches(_):
                yield Completion(
                    text=_,
                    start_position=-len(word_before_cursor),
                )

    ##############################################

    def get_completions(
            self,
            document: Document,
            complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        # Get command info
        line = document.current_line.lstrip()
        # remove multiple spaces
        line = re.sub(' +', ' ', line)
        number_of_parameters = line.count(' ')
        command = None
        right_word = None
        parameter_type = None
        if number_of_parameters:
            # words = [_ for _ in line.split(' ') if _]
            # command = words[0]
            index = line.rfind(' ')
            right_word = line[index+1:]
            index = line.find(' ')
            command = line[:index]
            try:
                func = getattr(Cli, command)
                signature = inspect.signature(func)
                parameters = list(signature.parameters.values())
                if len(parameters) > 1:
                    parameter = parameters[number_of_parameters]   # 0 is self
                    parameter_type = parameter.annotation.__name__   # Fixme: case type alias ???
            except AttributeError:
                pass
        # print(f'Debug: "{command}" | "{right_word}" | {number_of_parameters} | {parameter_type}')

        separator = ' '
        get_word_before_cursor = self._get_word_before_cursor1

        def handle_cd(root_path, current_path, right_word, folder: bool):
            if '/' in right_word:
                nonlocal separator
                separator = '/'
            if right_word.startswith('/'):
                current_path = root_path
            cwd = current_path.find(right_word)
            if folder:
                return cwd.folder_names
            else:
                # return cwd.leaf_names
                return cwd.leaf_names + cwd.folder_names

        if command is None:
            # case "du" -> "dump"
            words = self._commands
        elif document.current_char == ' ' and document.cursor_position < (len(document.current_line) - 1):
            # case "du /foo" -> "dump /foo"
            words = self._commands
            get_word_before_cursor = self._get_word_before_cursor2
        else:
            # case "dump " -> "dump /foo"
            words = ()
            match parameter_type:
                case 'bool':
                    words = ('true', 'false')
                case 'CommandName':
                    words = self._commands
                case 'FilePath':
                    # match command:
                    #     case 'create' | 'update':
                    cwd = Path().cwd()
                    filenames = sorted(cwd.glob('*.md'))
                    words = [_.name for _ in filenames]
                case 'PagePath':
                    words = handle_cd(self._cli._page_tree, self._cli._current_path, right_word, folder=False)
                case 'PageFolder':
                    words = handle_cd(self._cli._page_tree, self._cli._current_path, right_word, folder=True)
                case 'AssetFolder':
                    words = handle_cd(self._cli._asset_tree, self._cli._current_asset_folder, right_word, folder=True)
                case 'Tag':
                    # Fixme: 'list[Tag]' type is list
                    # Fixme: tag can have space !
                    words = [_.tag for _ in self._cli._api.tags()]
        yield from self._get_completions(document, complete_event, words, separator, get_word_before_cursor)

####################################################################################################

class Cli:

    ##############################################

    @staticmethod
    def _to_bool(value: str) -> bool:
        if isinstance(value, bool):
            return value
        match str(value).lower():
            case 'true' | 't':
                return True
            case _:
                return False

    ##############################################

    @classmethod
    def _fix_extension(self, filename: str, content_type: str = 'markdown') -> Path:
        extension = Page.extension_for(content_type)
        if not filename.endswith(extension):
            filename += extension
        return Path(filename)

    ############################################################################

    def __init__(self, api: WikiJsApi) -> None:
        self._api = api
        self.COMMANDS = [
            _
            for _ in dir(self)
            if not (_.startswith('_') or _[0].isupper() or _ in ('cli', 'run', 'print'))
        ]
        self.COMMANDS.sort()
        # self._completer = WordCompleter(self.COMMANDS)
        self._completer = CustomCompleter(self, self.COMMANDS)
        self._page_tree = None
        self._current_path = None
        self._asset_tree = None
        self._current_asset_folder = None

    ##############################################

    def _run_line(self, query: str) -> bool:
        # try:
        command, *argument = query.split()
        # except ValueError:
        #     if query.strip() == 'quit':
        #         return False
        # print(f"|{command}|{argument}|")
        try:
            if command == 'quit':
                return False
            method = getattr(self, command)
            try:
                method(*argument)
            except KeyboardInterrupt:
                self.print(f"{LINESEP}<red>Interrupted</red>")
            except ApiError as e:
                self.print(f'API error: <red>{e}</red>')
            except CommandError as e:
                self.print(e)
            except Exception as e:
                print(traceback.format_exc())
                print(e)
        except AttributeError:
            self.print(f"<red>Invalid command</red> <blue>{query}</blue>")
            self.usage()
        return True

    ##############################################

    def run(self, query: str) -> bool:
        commands = filter(bool, [_.strip() for _ in query.split(';')])
        for _ in commands:
            if not self._run_line(_):
                return False
        return True

    ##############################################

    def cli(self, query: str) -> None:
        self.print("<red>Build tree...</red>")
        self._init()
        self.print("<red>Done</red>")

        if query:
            if not self.run(query):
                return

        history = FileHistory(config.CLI_HISTORY_PATH)
        session = PromptSession(
            completer=self._completer,
            history=history,
        )
        self.usage()
        while True:
            try:
                message = [
                    ('class:prompt', '> '),
                ]
                query = session.prompt(
                    message,
                    style=STYLE,
                )
            # except KeyboardInterrupt:
            #     continue
            except EOFError:
                break
            else:
                if query:
                    if not self.run(query):
                        break
                else:
                    self.usage()

    ##############################################

    def print(self, message: str = '') -> None:
        printc(message)

    ##############################################

    def _absolut_path(self, path: str) -> PurePosixPath:
        if not path.startswith('/') and self._current_path:
            path = self._current_path.join(path)
        return PurePosixPath(path)

    ############################################################################

    def clear(self) -> None:
        """Clear the console"""
        shortcuts.clear()

    ############################################################################
    #
    # Help
    #

    def usage(self) -> None:
        """Show usage"""
        for _ in (
            "<red>Enter</red>: <blue>command argument</blue>",
            "    or <blue>command1 argument; command2 argument; ...</blue>",
            "<red>Commands are</red>: " + ', '.join([f"<blue>{_}</blue>" for _ in self.COMMANDS]),
            "use <blue>help</blue> <green>command</green> to get help",
            "use <green>tab</green> key to complete",
            "use <green>up/down</green> key to navigate history",
            "<red>Exit</red> using command <blue>quit</blue> or <blue>Ctrl+d</blue>"
        ):
            self.print(_)

            # "  <blue>dump</blue> <green>@page_url@ [output]</green>: dump the page",
            # "  <blue>list</blue>: list all the pages",
            # "  <blue>move</blue> <green>@page_url@ @new_page_url@</green>: move a page",
            # "  <blue>update</blue> <green>@page_url@ input</green>: update the page",
            # "  <blue>create</blue> <green>input</green>: create a page",
            # "  <blue>template</blue> <green>output</green>: create a page template",
            # "  <blue>check</blue>: check pages",
            # "  <blue>asset</blue>: list all the assets",
            # "  <blue>sync</blue>: sync wiki on disk",
            # "  <blue>git_sync</blue>: sync wiki on a Git repo",

    ##############################################

    def _help(self, command: CommandName = None, show_parameters: bool = False) -> None:
        func = getattr(self, command)
        # help(func)
        self.print(f'<green>{command:16}</green> <blue>{func.__doc__ or ''}</blue>')
        if show_parameters:
            signature = inspect.signature(func)
            for _ in signature.parameters.values():
                if _.default != inspect._empty:
                    default = f' = <orange>{_.default}</orange>'
                else:
                    default = ''
                self.print(f'  <blue>{_.name}</blue>: <green>{_.annotation.__name__}</green>{default}')


    def help(self, command: CommandName = None) -> None:
        """Show command help"""
        if command is None:
            for command in self.COMMANDS:
                self._help(command)
        else:
            self._help(command, show_parameters=True)

    ############################################################################
    #
    # Reset
    #

    def reset(self) -> None:
        """Reset page and folder tree"""
        # Fixme: can be slow
        self._page_tree = self._api.build_page_tree(ProgressBar)
        self._asset_tree = self._api.build_asset_tree()
        self._current_path = self._page_tree
        self._current_asset_folder = self._asset_tree
        # reset current_path ?

    def _init(self) -> None:
        if self._page_tree is None:
            self.reset()

    ############################################################################

    def emc(self, dst: FilePath) -> None:
        """Open a file in Emacs"""
        dst = self._fix_extension(dst)
        subprocess.Popen(('/usr/bin/emacsclient', dst), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ############################################################################
    #
    # CD
    #

    def cd(self, path: PageFolder) -> None:
        """Change the current path"""
        self._init()
        if path == '..':
            if not self._current_path.is_root:
                self._current_path = self._current_path.parent
        else:
            if path.startswith('/'):
                _ = self._page_tree.find(path[1:])
            else:
                _ = self._current_path.find(path)
            if _.is_leaf:
                self.print(f"<red>Error: </red> <blue>{path}</blue> <red>is not a folder</red>")
            else:
                self._current_path = _
        self.print(f"<red>moved to</red> <blue>{self._current_path.path}</blue>")

    ##############################################

    def cda(self, path: AssetFolder) -> None:
        """Change the current asset folder"""
        self._init()
        if path == '..':
            if not self._current_asset_folder.is_root:
                self._current_asset_folder = self._current_asset_folder.parent
        else:
            _ = self._current_asset_folder.find(path)
            if _.is_leaf:
                self.print(f"<red>Error: </red> <blue>{path}</blue> <red>is not a folder</red>")
            self._current_asset_folder = _
        self.print(f"<red>moved to</red> <blue>{self._current_asset_folder.path}</blue>")

        # try:
        #     self._current_asset_folder = self._asset_folders[path]
        #     self.print(f"<red>moved to</red> <blue>{path}</blue>")
        # except KeyError:
        #     self.print(f"<red>Error:</red> <blue>{path}</blue> <red>not found</red>")

    ##############################################

    def cwd(self) -> None:
        """Show current working directry"""
        self.print(f"<blue>Current path</blue> <green>{self._current_path.path}</green>")
        self.print(f"<blue>Current asset path</blue> <green>{self._current_asset_folder}</green>")

    ############################################################################
    #
    # Page Tree
    #

    # list clashes with list[]

    def pages(self, complete: bool = False) -> None:
        """List the pages"""
        complete = self._to_bool(complete)
        for page in self._api.list_pages():
            if complete:
                # page.complete()
                self.print(f"<green>{page.path_str:60}</green> <blue>{page.title:40}</blue> {len(page.content):5} @{page.locale} {page.id:3}")
            else:
                self.print(f"<green>{page.path_str:60}</green> <blue>{page.title:40}</blue> @{page.locale} {page.id:3}")

    ##############################################

    def with_path(self, path: PagePath) -> None:
        """List the pages matching a path pattern"""
        for page in self._api.list_pages():
            if path in page.path.lower():
                self.print(f"<green>{page.path:60}</green> <blue>{page.title:40}</blue> @{page.locale} {page.id:3}")

    ##############################################

    # def with_tags(self, *tags: list[Tag]) -> None:
    def with_tags(self, tag1: Tag, tag2: Tag = None, tag3: Tag = None, tag4: Tag = None) -> None:
        """List the pages having those tags"""
        tags = [_ for _ in (tag1, tag2, tag3, tag4) if _]
        for page in self._api.list_page_for_tags(tags):
            self.print(f"<green>{page.path_str:60}</green> <blue>{page.title:40}</blue> @{page.locale} {page.id:3}")

    ##############################################

    def search(self, query: str) -> None:
        """Search page"""
        response = self._api.search(query)
        if response.suggestions:
            _ = ', '.join(response.suggestions)
            self.print(f'Suggestions: <blue>{_}</blue>')
        for _ in response.results:
            self.print(f'<blue>{_.path:60}</blue> <green>{_.title}</green>')

    ##############################################

    def last(self) -> None:
        """List the last updated pages"""
        for page in self._api.list_pages(order_by='UPDATED', reverse=True, limit=10):
            self.print(f"<green>{page.path_str:60}</green> <blue>{page.title:40}</blue>{LINESEP}  {page.updated_at}   @{page.locale}   {page.id:3}")

    ##############################################

    def tree(self, path: PagePath) -> None:
        """Show page tree"""
        path = self._absolut_path(path)
        items = list(self._api.tree(path))
        # items.sort(key=lambda _: _.path)
        items = usorted(items, 'path_str')
        for item in items:
            is_folder = '/' if item.isFolder else ''
            path = f"{item.path}{is_folder}"
            self.print(f"<green>{path:60}</green> <blue>{item.title:40}</blue> #{item.id}")

    def itree(self, id: int) -> None:
        """Show page tree"""
        # items = list(self._api.itree(id))
        items = self._api.itree(id)
        items = usorted(items, 'path_str')
        for item in items:
            is_folder = '/' if item.isFolder else ''
            path = f"{item.path}{is_folder}"
            self.print(f"<green>{path:60}</green> <blue>{item.title:40}</blue> #{item.id}")

    ##############################################

    def ls(self) -> None:
        """List the current path"""
        self._init()
        self.print(f"<red>CWD</red> <blue>{self._current_path.path}</blue>")
        # for _ in self._current_path.folder_childs:
        #     self.print(f"  {_.name}")
        for _ in self._current_path.childs:
            if _.is_folder:
                if _.page is not None:
                    has_page = f' : <orange>{_.page.title}</orange>'
                else:
                    has_page = ''
                self.print(f"  <green>{_.name} /</green>{has_page}")
            else:
                self.print(f"  <blue>{_.name}</blue> : <orange>{_.page.title}</orange>")

    ############################################################################
    #
    # Page
    #

    def template(self, dst: FilePath, path: PagePath = None, locale: str = 'fr', content_type: str = 'markdown') -> None:
        """Write a page template"""
        dst = self._fix_extension(dst)
        if self._current_path:
            if path is None:
                path = dst.stem
            path = self._current_path.join(path)
            self.print(f"<red>Path is</red> <blue>{path}</blue>")
        elif path is None:
            self.print("<red>path is required</red>")

        if Page.template(dst, locale, path, content_type) is None:
            self.print(f"<red>Error: file exists</red>")
        else:
            self.print(f"<red>Wrote</red>  <blue>{dst}</blue>")

    ##############################################

    def create(self, input: FilePath) -> None:
        """Create a new page"""
        input = self._fix_extension(input)
        page = Page.read(input, self._api)
        if page.title is None:
            self.print(f"<red>Error: missing title</red>")
            return
        _ = f"<green>{page.path_str}</green> @{page.locale}{LINESEP}"
        _ += f"  <blue>{page.title}</blue>{LINESEP}"
        self.print(_)
        response = page.create()
        self.print(f"<red>{response.message}</red>")

    ##############################################

    def dump(self, path: PagePath, output: str = None) -> None:
        """dump a page"""
        path = self._absolut_path(path)
        page = self._api.page(path)   # locale=
        # page.complete()
        # Fixme: write dump on stdout
        _ = f"<green>{page.path_str}</green> @{page.locale}{LINESEP}"
        _ += f"  <blue>{page.title}</blue>{LINESEP}"
        _ += f"  {page.id}{LINESEP}"
        self.print(_)
        if output:
            output = page.add_extension(output)
            if output.exists():
                self.print(f"<red>File exists</red> {output}")
            else:
                self.print(f"<blue>Write</blue> {output}")
                page.write(output)
        else:
            rule = '\u2500' * 100
            print(rule)
            # print(page.content)
            print(page.export())
            print(rule)

    ##############################################

    def open(self, path: PagePath, locale: str = 'fr') -> None:
        """Open a page in the browser"""
        path = self._absolut_path(path)
        url = f'{self._api.api_url}/{locale}/{path}'
        self.print(f"<red>Open</red>  <blue>{url}</blue>")
        subprocess.Popen(('/usr/bin/xdg-open', url), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ##############################################

    def history(self, path: PagePath) -> None:
        """Show page history"""
        path = self._absolut_path(path)
        page = self._api.page(path)   # locale=
        # page.complete()
        history = page.history
        number_of_versions = len(history)
        # print(f"{number_of_versions+1:4} {date2str(page.updated_at)}")
        for i, ph in enumerate(history):
            # {ph.actionType}
            action = []
            if ph.is_initial:
                action.append('initial')
            elif ph.is_edited:
                action.append('edited')
            moved = ph.is_moved
            if moved:
                action.append('moved')
            action = ' '.join(action)
            if action:
                action = f'<blue>{action}</blue>'
            else:
                prev_ph = ph.prev
                if prev_ph and not page.same_metadata(prev_ph.page_version):
                    # print(page.metadata)
                    # print(prev_ph.page_version.metadata)
                    action = f'<blue>metadata</blue>'
                else:
                    # Fixme: ok ???
                    action = '<orange>ghost</orange>'
            self.print(f"{number_of_versions-i:4} {ph.date_str} {action}")
            if moved:
                old_path, new_path = moved
                self.print(' '*10 + f'<green>{old_path}</green> -> <green>{new_path}</green>')
            # print(f"      {ph.actionType} : {ph.valueBefore} -> {ph.valueAfter}")
            # pv = ph.page_version
            # if pv is not None:
            #     print(f"      {pv.action}")

    ##############################################

    def diff(self, input: FilePath = None) -> None:
        """Diff a page"""
        file_page = Page.read(input, self._api)
        wiki_page = file_page.reload()
        # wiki_page.complete()
        self.print(f"<red>Wiki:</red> <blue>{wiki_page.updated_at}</blue>")
        self.print(f"<red>File:</red> <blue>{file_page.updated_at}</blue>")
        for _ in difflib.unified_diff(
                wiki_page.content.splitlines(),
                file_page.content.splitlines(),
                fromfile='wiki',
                tofile='disk',
                n=3,
                lineterm='',
        ):
            _ = html.escape(_)
            if _.startswith('---') or _.startswith('+++'):
                _ = f'<green>{_}</green>'
            elif _.startswith('@@'):
                _ = f'<blue>{_}</blue>'
            elif _.startswith('-'):
                _ = f'<red>-</red>{_[1:]}'
            elif _.startswith('+'):
                _ = f'<green>+</green>{_[1:]}'
            self.print(_)

    ##############################################

    def update(self, input: FilePath = None) -> None:
        """Update a page"""
        page = Page.read(input, self._api)
        _ = f"<green>{page.path_str}</green> @{page.locale}{LINESEP}"
        _ += f"  <blue>{page.title}</blue>{LINESEP}"
        _ += f"  {page.id}{LINESEP}"
        self.print(_)
        response = page.update()
        self.print(f"<red>{response.message}</red>")

    ##############################################

    def movep(self, old_path: PagePath, new_path: PagePath, dryrun: bool = False) -> None:
        """Move the pages that match the path pattern"""
        # <pattern>/... -> <new_pattern>/...
        # relative page -> folder
        dryrun = self._to_bool(dryrun)
        # self.print(f"  Move: <green>{old_path}</green> <red>-></red> <blue>{new_path}</blue>")
        for page in self._api.list_pages():
            path = page.path
            if path.startswith(old_path):
                dest = path.replace(old_path, new_path)
                self.print(f"  Move page: <green>{path}</green> <red>-></red> <blue>{dest}</blue>")
                if not dryrun:
                    response = page.move(dest)
                    self.print(f"<red>{response.message}</red>")

    ##############################################

    def _move_impl(self, path: str, new_path: str, rename: bool = False, dryrun: bool = False) -> None:
        """Move a page"""
        path = self._absolut_path(path)
        page = self._api.page(path)   # locale=
        new_path = self._absolut_path(new_path)
        if not rename:
            dest = new_path.joinpath(page.path.name)
        self.print(f"  Move page: <green>{path}</green> <red>-></red> <blue>{dest}</blue>")
        dryrun = self._to_bool(dryrun)
        if not dryrun:
            response = page.move(dest)
            self.print(f"<red>{response.message}</red>")


    def move(self, path: PagePath, new_path: PageFolder, dryrun: bool = False) -> None:
        """Move a page"""
        self._move_impl(path, new_path, dryrun)


    def rename(self, path: PagePath, new_path: PagePath, dryrun: bool = False) -> None:
        """Rename a page"""
        self._move_impl(path, new_path, rename=True, dryrun=dryrun)

    ############################################################################
    #
    # Tags
    #

    def tags(self) -> None:
        """List the tags"""
        for _ in usorted(self._api.tags(), 'tag'):
            self.print(f'<blue>{_.tag:30}</blue> <green>{_.title}</green>')

    ##############################################

    def search_tags(self, query: str) -> None:
        """Search the tags"""
        for _ in self._api.search_tags(query):
            self.print(f'<blue>{_}</blue>')

    ############################################################################
    #
    # Asset
    #

    def lsa(self) -> None:
        """List the current asset folder"""
        self._init()
        self.print(f"<red>CWD</red> <blue>{self._current_asset_folder.path}</blue>")
        # for _ in self._current_path.folder_childs:
        #     self.print(f"  {_.name}")
        for _ in self._current_asset_folder.childs:
            if _.is_folder:
                self.print(f"  <green>{_.name} /</green>")
            else:
                self.print(f"  <blue>{_.name}</blue>")

    ##############################################

    def asset(self, show_files: bool = True, show_folder_path: bool = False) -> None:
        """List the assets"""
        show_files = self._to_bool(show_files)
        def show_folder(folder_id: int = 0, indent: int = 0, stack: list = []):
            indent_str = '  '*indent
            if show_files:
                for asset in self._api.list_asset(folder_id):
                    self.print(f"{indent_str}- <blue>{asset.filename}</blue>   {asset.updated_at}   <green>{asset.id}</green>")
                    url = '/'.join([self._api.api_url] + stack + [asset.filename])
                    self.print(f"{indent_str}  {url}")
            for _ in self._api.list_asset_subfolder(folder_id):
                path = '/'.join(stack + [_.name])
                # print(f"{indent_str}- {_.name} {_.slug} {_.id}")
                if show_folder_path:
                    self.print(f"<red>{path}</red>    <green>{_.id}</green>")
                else:
                    self.print(f"{indent_str}+ <red>{_.name}</red>    <green>{_.id}</green>")
                show_folder(_.id, indent + 1, stack + [_.name])
        self.print('<blue>/</blue>')
        show_folder()

    ##############################################

    def upload(self, path: FilePath, name: str = None) -> None:
        """Upload an asset"""
        if self._current_asset_folder is not None:
            self._current_asset_folder.upload(path, name)
            # lists asset folder
            assets = list(self._current_asset_folder.list())
            assets.sort(key=lambda _: _.updated_at, reverse=True)
            self.print(f'<blue>{self._current_asset_folder.path}</blue>')
            for asset in assets:
                self.print(f'- <blue>{asset.filename}</blue>   {asset.updated_at}')
        else:
            self.print(f"<red>Error: run cd_asset before</red>")

    ############################################################################
    #
    # Sync
    #

    def sync(self, path: Path = None) -> None:
        """Sync on disk"""
        if path is None:
            path = Path('.', 'sync')
        sync.sync(self._api, path)

    ##############################################

    def sync_asset(self, path: Path = None) -> None:
        """Sync assets on disk"""
        if path is None:
            path = Path('.', 'sync_asset')
        sync.sync_asset(self._api, path)

    ##############################################

    def git_sync(self, path: Path = None) -> None:
        """Sync Git repo"""
        if path is None:
            GIT_SYNC = 'git_sync'
            path = Path('.', GIT_SYNC)
        sync.git_sync(self._api, path)

    ############################################################################
    #
    # Check
    #

    def check(self) -> None:
        """Check pages"""
        pages = list(self._api.list_pages())
        page_paths = [_.path for _ in pages]
        for page in pages:
            # print(f"Checking {page.path_str}")
            # page.complete()
            dead_links = []
            for line in page.content.splitlines():
                start = 0
                while True:
                    i = line.find('](', start)
                    if i != -1:
                        start = i+2
                        j = line.find(')', start)
                        if j != -1:
                            path = line[start:j].strip()
                            if path.startswith('/'):
                                path = path[1:]
                            _ = path.rfind('.')
                            if _ != -1:
                                extension = path[_:]
                            else:
                                extension = None
                            if (not re.match('^https?\\://', path)
                                and extension not in ('.png', '.jpg', '.webp', '.ods', '.pdf')
                                and path not in page_paths):
                                message = f"  <green>{path}</green>{LINESEP}    |{line}"
                                if path:
                                    parts = path.split('/')
                                    name = parts[-1]
                                    for _ in page_paths:
                                        name2 = _.split('/')[-1]
                                        if name in name2:
                                            message += f"{LINESEP}    <blue>found</blue> <green>{_}</green>"
                                    dead_links.append(message)
                    else:
                        break
            if dead_links:
                _ = f"<red>Page</red> <blue>{page.url}</blue> <red>as deak link</red>" + LINESEP
                _ += LINESEP.join(dead_links)
                self.print(_)

    ##############################################

    def links(self) -> None:
        """List the page links"""
        pages = list(self._api.links())
        # pages.sort(key=lambda _: _.path)
        pages = usorted(pages, 'path')
        for page in pages:
            self.print(f'<blue>{page.path:60}</blue>')
            # sorted()
            for _ in page.links:
                self.print(f'  <green>{_}</green>')
