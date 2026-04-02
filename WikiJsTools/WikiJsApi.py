####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['ApiError', 'WikiJsApi', 'Node', 'Page']

# Fime: use PurePosixPath

####################################################################################################

from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path, PurePosixPath
from pprint import pprint
from typing import Any
from typing import Iterator

import os
import types

import requests

from . import config
from . import query as Q
from .date import date2str
from .node import Node
from .printer import printc, html_escape
from time import time

LINESEP = os.linesep

####################################################################################################

# GraphQL
#  !
#    By default, all value types in GraphQL can result in a null value.
#    If a value type includes an exclamation point, it means that value cannot be null.

####################################################################################################

@dataclass
class ResponseResult:
    succeeded: bool
    errorCode: int
    slug: str
    message: str

####################################################################################################

@dataclass
class Tag:
    id: int
    tag: str
    title: str
    createdAt: str
    updatedAt: str

####################################################################################################

@dataclass
class PageTreeItem:
    api: 'WikiJsApi'

    id: int
    path: PurePosixPath
    depth: int
    title: str
    isPrivate: bool
    isFolder: bool
    privateNS: str
    parent: int
    pageId: int
    locale: str

    ##############################################

    def __post_init__(self):
        # Fixme: see BasePage
        self.path = PurePosixPath(self.path)

    ##############################################

    @property
    def path_str(self) -> str:
        return str(self.path)

####################################################################################################

class BasePage:

    RULE = '-'*50

    @property
    def split_path(self) -> list[str]:
        return str(self.path).split('/')

    @property
    def path_str(self) -> str:
        return str(self.path)

    ##############################################

    @property
    def url(self) -> str:
        return f'{self.api.api_url}/{self.locale}/{self.path}'

    ##############################################

    METADATA_ATTRIBUTES = (
        'title',
        'description',
        'tags',
        # 'locale',
        # 'isPublished',
        # 'isPrivate',
        # 'privateNS',
        # 'publishStartDate',
        # 'publishEndDate',
        # 'scriptCss',
        # 'scriptJs',
    )

    @property
    def metadata(self) -> dict:
        return {_: getattr(self, _) for _ in self.METADATA_ATTRIBUTES}

    # Fixme: is_same_metadata
    def same_metadata(self, obj: 'PageBase') -> bool:
        for _ in self.METADATA_ATTRIBUTES:
            if getattr(self, _) != getattr(obj, _):
                return False
        return True

    ##############################################

    @staticmethod
    def extension_for(content_type: str = 'markdown'):
        match content_type:
            case 'markdown':
                return '.md'
            case _:
                return '.txt'

    ##############################################

    @classmethod
    def file_path_impl(
            cls,
            dst: Path | str,
            locale: str,
            path: str = None,
            content_type: str = 'markdown',
    ) -> Path:
        _ = str(path).split('/')
        _[-1] += cls.extension_for(content_type)
        return Path(dst).joinpath(locale, *_)

    ##############################################

    def file_path(self, dst: Path | str, path: str = None) -> Path:
        # Note: path is used to move page version
        if path is None:
            path = self.path
        return self.file_path_impl(dst, self.locale, path, self.contentType)

    ##############################################

    def add_extension(self, dst: str) -> Path:
        extension = self.extension_for(self.contentType)
        if not dst.endswith(extension):
            dst += extension
        return Path(dst)

    ##############################################

    @classmethod
    def template(
            cls,
            dst: Path | str,
            locale: str,
            path: str = None,
            content_type: str = 'markdown',
            check_exists: bool = True,
    ) -> Path:
        dst = Path(dst)
        if check_exists and dst.exists():
            return

        data = ''
        # data += cls.RULE + LINESEP
        for field, value in dict(
                title='',
                locale=locale,
                path=path,
                description='',
                tags=[],
                # createdAt='',
                # updatedAt='',

                isPublished=True,
                isPrivate=False,
                privateNS=None,
                contentType=content_type,
        ).items():
            data += f'{field}: {value}' + LINESEP
        data += cls.RULE + LINESEP
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(data, encoding='utf8')
        return dst

    ##############################################

    def sync(self, dst: Path | str, check_exists: bool = True) -> Path:
        file_path = self.file_path(dst)
        if check_exists:
            # Check updatedAt
            file_date = None
            if file_path.exists():
                with open(file_path, 'r') as fh:
                    for line in fh:
                        if line.startswith('updatedAt'):
                            i = line.find(':')
                            _ = line[i+1:].strip()
                            file_date = datetime.fromisoformat(_)
                            break
            if file_date is not None:
                # print(f'{self.path} | {old_date} vs {new_date}')
                if file_date == self.updated_at:
                    return
        self.write(file_path)
        return file_path

    ##############################################

    @classmethod
    def export_tags(cls, tags: list[str]) -> str:
        return '[' + ', '.join(["'" + _.replace("'", r"\'") + "'" for _ in tags]) + ']'

    @classmethod
    def import_tags(cls, tags: str) -> list[str]:
        if tags[0] != '[' or tags[-1] != ']':
            raise ValueError()
        def on_tag(tag):
            tag = tag.strip()
            if tag[0] != tag[-1] != "'":
                raise ValueError()
            return tag[1:-1]
        return [on_tag(_) for _ in tags[1:-1].split(',')]

    ##############################################

    def export(self) -> str:
        data = ''
        # data += self.RULE + LINESEP
        for field in (
                'title',
                'locale',
                'path',
                'description',
                'tags',
                'createdAt',
                'updatedAt',

                'id', 'pageId',
                'versionId',
                'versionDate',
                'isPublished',
                'isPrivate',
                'privateNS',
                'contentType',
        ):
            try:
                value = getattr(self, field)
                match field:
                    case 'pageId':
                        field = 'id'
                    case 'tags':
                        value = self.export_tags(value)
                    # True/False -> True/False
                data += f'{field}: {value}' + LINESEP
            except AttributeError:
                # for example updatedAt
                pass
        data += self.RULE + LINESEP
        # keep trailing end line / .rstrip()
        data += self.content
        return data

    @property
    def bytes_data(self) -> str:
        if not hasattr(self, '_bytes_data'):
            self._bytes_data = self.export().encode('utf8')
        return self._bytes_data

    @property
    def bytes_size(self) -> int:
        return len(self.bytes_data)

    ##############################################

    def write(self, dst: Path | str) -> Path:
        path = Path(dst)
        data = self.export()
        path.parent.mkdir(parents=True, exist_ok=True)
        # if not path.exists():
        path.write_text(data, encoding='utf8')
        return path

    ##############################################

    @classmethod
    def import_(self, lines: str, api: 'WikiJsApi') -> 'Page':
        data = dict(id=None, createdAt=None, updatedAt=None)
        # Fixme: we must keep content as it is
        offset = 0
        for line in lines.splitlines(keepends=True):
            offset += len(line)
            sline = line.strip()
            if sline == self.RULE:
                break
            else:
                index = sline.find(":")
                key = sline[:index].strip()
                value = sline[index+1:].strip()
                match key:
                    case 'id':
                        if value:
                            value = int(value)
                    case 'tags':
                        value = self.import_tags(value)
                    case 'isPublished' | 'isPrivate':
                        value = value == 'True'
                data[key] = value
        content = lines[offset:]
        # Ensure trailing line sep
        # content = content.strip() + LINESEP
        #! data['content'] = content
        print('pprint data')
        pprint(data)
        pprint(content)
        page = Page(api, **data)
        page._content = content
        return page

    @classmethod
    def read(self, input: Path | str, api: 'WikiJsApi') -> 'Page':
        input = Path(input)
        lines = input.read_text()
        return self.import_(lines, api)

####################################################################################################

@dataclass
class Page(BasePage):
    # Merge PageListItem
    #  irrelevant attributes are set to None

    api: 'WikiJsApi'

    path: PurePosixPath
    locale: str

    title: str
    description: str
    contentType: str
    tags: list[str]

    createdAt: str
    updatedAt: str

    isPublished: bool

    isPrivate: bool
    privateNS: str

    id: int = None

    publishStartDate: str = None
    publishEndDate: str = None

    authorId: int = None
    authorName: str = None
    authorEmail: str = None

    creatorId: int = None
    creatorName: str = None
    creatorEmail: str = None

    hash: str = None
    render: str = None
    editor: str = None
    scriptCss: str = None
    scriptJs: str = None
    toc: str = None

    # see property
    # content: str = None

    ##############################################

    def __post_init__(self):
        self.path = PurePosixPath(self.path)

    ##############################################

    @property
    def content(self) -> None:
        # Fixme: not hasattr(self, '_content')
        if '_content' not in self.__dict__:
            self.api.complete_page(self)
        return self._content

    @property
    def history(self) -> list['PageHistory']:
        # order is newer first
        # the first one corresponds to the previous version !
        # Fixme: not hasattr(self, '_history')
        if '_history' not in self.__dict__:
            current = PageHistory(
                api=self.api,
                page=self,
                versionDate=self.updatedAt,
                authorId=self.authorId,
                authorName=self.authorName,
                actionType='edit',
            )
            history = [current]
            history += self.api.page_history(self)
            number_of_versions = len(history)
            for i in range(number_of_versions):
                if i + 1 < number_of_versions:
                    history[i].prev = history[i+1]
                if i > 0:
                    history[i].next = history[i-1]
            self._history = history
            # self._history_map = {_.versionId: _ for _ in self._history}
        return self._history

    ##############################################

    @property
    def created_at(self) -> datetime:
        if self.createdAt:
            return datetime.fromisoformat(self.createdAt)
        else:
            return None

    @property
    def updated_at(self) -> datetime:
        if self.updatedAt:
            return datetime.fromisoformat(self.updatedAt)
        else:
            return None

    ##############################################

    def create(self, *args, **kwargs) -> 'ResponseResult':
        return self.api.create_page(self, *args, **kwargs)

    def update(self, *args, **kwargs) -> 'ResponseResult':
        return self.api.update_page(self, *args, **kwargs)

    def move(self, *args, **kwargs) -> 'ResponseResult':
        return self.api.move_page(self, *args, **kwargs)

    ##############################################

    def reload(self) -> 'Page':
        return self.api.page(self.path, self.locale)

####################################################################################################

@dataclass
class PageVersion(BasePage):
    """Store a previous page version"""
    api: 'WikiJsApi'
    page: Page

    # Page
    pageId: int   # Fixme: Page.id
    path: str
    locale: str

    title: str
    description: str
    contentType: str
    tags: list[str]

    createdAt: str
    # updatedAt ->
    versionDate: str   # == PageHistory.versionDate

    isPublished: bool
    publishEndDate: str
    publishStartDate: str

    isPrivate: bool
    # privateNS: str

    editor: str

    #  == PageHistory.
    authorId: str
    authorName: str

    content: str

    # Version
    versionId: int   # == PageHistory.versionId
    action: str      # != PageHistory.actionType

    ##############################################

    @property
    def id(self) -> int:
        return self.pageId

    ##############################################

    # @property
    # def prev(self) -> 'PageVersion':
    #     # print(f"prev for {self.versionId}")
    #     for i, _ in enumerate(self.page.history):
    #         # print(f"{i} {_}")
    #         if _.versionId == self.versionId:
    #             break
    #     try:
    #         _ = self.page.history[i+1]
    #         # print(f"{i+1} {_}")
    #         # print(f"{_.versionId} -> {self.versionId}")
    #         return _.page_version
    #     except IndexError:
    #         return None

    # @property
    # def old_path(self) -> str:
    #     return self.prev.path

####################################################################################################

@dataclass
class PageHistory:
    """Summarise a page version"""
    api: 'WikiJsApi'
    page: Page

    # == PageVersion.
    versionDate: str
    authorId: int
    authorName: str

    actionType: str   # != PageVersion.action

    # == PageVersion.
    versionId: int = None   # to fake the current version

    # used for actionType = 'move'
    valueBefore: str = None  # aka old path
    valueAfter: str = None   # aka move path

    # history links
    prev: 'PageHistory' = None
    next: 'PageHistory' = None

    ##############################################

    @property
    def is_current(self) -> bool:
        # Fixme: could be updated on server
        # return self.versionDate == self.page.updatedAt
        return self.versionId is None

    @property
    def is_initial(self) -> bool:
        return self.prev is None

    ##############################################

    @property
    def page_version(self) -> PageVersion:
        if self.versionId is None:
            # Fixme: could return self.page
            return None
        if '_page_version' not in self.__dict__:
            self._page_version = self.api.page_version(self)
        return self._page_version

    ##############################################

    @property
    def date(self) -> datetime:
        return datetime.fromisoformat(self.versionDate)

    @property
    def date_str(self) -> str:
        """Return local date"""
        return date2str(self.date)

    @property
    def date_utc_str(self) -> str:
        return self.versionDate

    ##############################################

    @property
    def changed(self) -> bool:
        return self.valueAfter != self.valueBefore

    @property
    def old_path(self) -> str:
        return self.valueBefore

    @property
    def new_path(self) -> str:
        return self.valueAfter

    ##############################################

    @property
    def wrapper(self) -> Page | PageVersion:
        if self.is_current:
            return self.page
        else:
            return self.page_version

    ##############################################

    def _compare(self, func):
        if self.prev is not None:
            prev = self.prev.page_version
            return func(self.wrapper, prev)
        # else initial
        return False

    @property
    def is_metadata_edited(self) -> bool:
        return self._compare(lambda _, prev: not _.same_metadata(prev))

    @property
    def is_edited(self) -> bool:
        return self._compare(lambda _, prev: _.content != prev.content)

    @property
    def is_moved(self) -> bool | tuple[str, str]:
        if self.actionType == 'moved':
            return (self.valueBefore, self.valueAfter)
        # but a move action can also be
        prev = self.prev
        if prev is not None:
            prev_pv = prev.page_version
            if prev_pv.action == 'moved':
                old_path = prev_pv.path
                new_path = self.path
                return (old_path, new_path)
        return False

    ##############################################

    @property
    def locale(self) -> str:
        return self.wrapper.locale

    @property
    def path(self) -> str:
        return self.wrapper.path

    @property
    def path_str(self) -> str:
        return self.wrapper.path_str

    @property
    def page_id(self) -> str:
        return self.wrapper.id

    @property
    def content(self) -> str:
        return self.wrapper.content

    def sync(self, *args, **kwargs) -> Path:
        return self.wrapper.sync(*args, **kwargs)

####################################################################################################

@dataclass
class PageLinkItem:
    id: int
    path: str
    title: str
    links: list[str]

####################################################################################################

@dataclass
class PageSearchResult:
    id: str
    title: str
    description: str
    path: str
    locale: str

@dataclass
class PageSearchResponse:
    results: list[PageSearchResult]
    suggestions: list[str]
    totalHits: int

####################################################################################################

@dataclass
class AssetFolder:
    api: 'WikiJsApi'

    id: int
    name: str
    slug: str

    path: str = None

    # parent: 'AssetFolder'

    ##############################################

    def list(self) -> Iterator['Asset']:
        yield from self.api.list_asset(self.id)

    ##############################################

    def upload(self, path: Path | str, name: str = None) -> None:
        self.api.upload(self.id, path, name)

####################################################################################################

@dataclass
class Asset:
    id: int
    filename: str
    ext: str
    kind: str
    mime: str
    fileSize: int
    metadata: str
    createdAt: str
    updatedAt: str

    path: str = None

    ##############################################

    @property
    def created_at(self) -> datetime:
        return datetime.fromisoformat(self.createdAt)

    @property
    def updated_at(self) -> datetime:
        return datetime.fromisoformat(self.updatedAt)

####################################################################################################

def xpath(data: dict, path: str) -> dict:
    d = data
    for _ in str(path).split('/'):
        d = d[_]
    return d

####################################################################################################

class ApiError(NameError):
    pass

####################################################################################################

class WikiJsApi:

    DEFAULT_EXPIRE_TIME = 5 * 60   # s

    ##############################################

    def __init__(self, api_url: str, api_key: str, expire_time: int = DEFAULT_EXPIRE_TIME) -> None:
        self._api_url = str(api_url)
        self._api_key = str(api_key)
        self._headers = {
            'Authorization': f'Bearer {api_key}',
            # 'content-type': 'application/json',
        }
        self._expire_time = int(expire_time)
        self._cache = {_: dict() for _ in ('itree', 'page')}
        self.info()

    ##############################################

    @property
    def api_url(self) -> str:
        return self._api_url

    ##############################################

    def is_valid_path(self, path: str) -> bool:
        # Space (use dashes instead)
        # Period (reserved for file extensions)
        # Unsafe URL characters (such as punctuation marks, quotes, math symbols, etc.)
        for c in path:
            if c in ' .,;!?&|+=*^~#%$@{}[]<>\\\'"':
                return False
        return True

    ##############################################

    def _lookup_cache(self, cache_name: str, key: str) -> Any | None:
        cache = self._cache[cache_name]
        now = time()
        cached = cache.get(key, None)
        if cached is not None:
            delta = now - cached[0]
            # printc(f"Cached {cache_name} {key}")
            if delta <= self._expire_time:
                return cached[1]
        return None

    def _store_cache(self, cache_name: str, key: str, value: Any):
        # printc(f"Cache {cache_name} {key}")
        cache = self._cache[cache_name]
        cache[key] = (time(), value)

    # Decorator
    # Fixme: do we need is_generator
    def cache(cache_name: str):
        def decorator(func):
            # print('Cache func', func)
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                cache = kwargs.pop('cache', True)
                cache_key = None
                value = None
                if cache:
                    parts = [str(_) for _ in args] + [f'{key}:{value}' for key, value in kwargs.items()]
                    cache_key = '/'.join(parts)
                    value = self._lookup_cache(cache_name, cache_key)
                    # if value is not None:
                    #     printc(f'Found in cache {cache_key}')
                if value is None:
                    # print(f'Call {func}')   # Fixme: <>
                    value = func(self, *args, **kwargs)
                    # We cannot mix return and yield in a function !
                    is_generator = isinstance(value, types.GeneratorType)
                    if is_generator:
                        value = list(value)
                    if cache:
                        self._store_cache(cache_name, cache_key, value)
                return value
            return wrapper
        return decorator

    ##############################################

    def query_wikijs(self, query: dict) -> dict:
        query['query'] = Q.clean_query(query['query'])
        if config.DEBUG:
            _ = Q.dump_query(query)
            printc(f"<blue>API Query:</blue> {_}")
        response = requests.post(f'{self._api_url}/graphql', json=query, headers=self._headers)
        # if response.status_code != requests.codes.ok:
        #     raise NameError(f"Error {response}")
        data = response.json()
        if 'errors' in data:
            d = data['errors'][0]
            path = '/'.join(d.get('path', ''))
            message = d['message']
            stacktrace = LINESEP.join(d['extensions']['exception']['stacktrace'])
            stacktrace = html_escape(stacktrace)
            location = d['locations'][0]['column']
            query = query['query']
            query_location = query[max(0, location-1):min(location+20, len(query))]
            message = f'{stacktrace}{LINESEP}{LINESEP}Path: {path}{LINESEP}@ {query_location}...{LINESEP}{LINESEP}{message}'
            raise ApiError(message)
        else:
            return data

    ############################################################################

    def get(self, url: str) -> bytes:
        url = f'{self._api_url}/{url}'
        response = requests.get(url, headers=self._headers)
        if response.status_code != requests.codes.ok:
            raise NameError(f"Error {response}")
        return response.content

    ##############################################

    def upload(self, folder_id: int, path: Path | str, name: str = None) -> None:
        path = Path(path).expanduser().resolve()
        if name is None:
            name = path.name
        payload = path.read_bytes()
        multipart_form_data = (
            ('mediaUpload', (None, '{"folderId":' + str(folder_id) + '}')),
            ('mediaUpload', (name, payload, 'image/png')),
        )
        # _ = requests.Request('POST', f'{self._api_url}/u', files=multipart_form_data)
        # print(_.prepare().body[:100])
        response = requests.post(f'{self._api_url}/u', files=multipart_form_data, headers=self._headers)
        if response.status_code != requests.codes.ok:
            raise NameError(f"Error {response}")
        # pprint(response)

    ############################################################################

    def info(self) -> None:
        query = {
            'query': Q.INFO,
        }
        data = self.query_wikijs(query)
        _ = xpath(data, 'data/system/info')
        # pprint(data)
        self._number_of_pages = _['pagesTotal']

    ############################################################################
    #
    # Page
    #

    @property
    def number_of_pages(self) -> int:
        return self._number_of_pages

    ##############################################

    def _to_path(self, path: str) -> str:
        path = str(path)
        # remove / from cd
        if path.startswith('/'):
            path = path[1:]
        return path

    ##############################################

    @cache(cache_name='page')
    def page(self, path: str, locale: str = 'fr') -> Page:
        path = self._to_path(path)
        query = {
            'variables': {
                'path': path,
                'locale': locale,
            },
            'query': Q.PAGE,
        }
        data = self.query_wikijs(query)
        _ = xpath(data, 'data/pages/singleByPath')
        _['tags'] = [_['tag'] for _ in _['tags']]
        # pprint(_)
        return Page(api=self, **_)

    ##############################################

    def complete_page(self, page: Page) -> None:
        query = {
            'variables': {
                'id': page.id,
            },
            'query': 'query ($id: Int!) {pages {single(id: $id) {content}}}',
        }
        data = self.query_wikijs(query)
        # pprint(data)
        page._content = xpath(data, 'data/pages/single/content')

    ##############################################

    def page_history(self, page: Page) -> None:
        # Return previous versions ordered form the last to the initial one
        query = {
            'variables': {
                'id': page.id,
            },
            'query': Q.PAGE_HISTORY,
        }
        data = self.query_wikijs(query)
        history = xpath(data, 'data/pages/history/trail')
        # _ = xpath(data, 'data/pages/history/total')
        return [PageHistory(api=self, page=page, **_) for _ in history]

    ##############################################

    def page_version(self, page_history: PageHistory = None) -> None:
        # /!\ the current version doesn't have a PageVersion
        # page: Page = None
        # if page is None and page_history is None:
        #     raise NameError("page or page_history is required")
        # if page is not None:
        #     id = page.id
        #     version_id = page.version_id
        # else:
        id = page_history.page.id
        version_id = page_history.versionId
        if version_id is None:
            raise ValueError("current version doesn't have PageVersion")
        query = {
            'variables': {
                'id': id,
                'version_id': version_id,
            },
            'query': Q.PAGE_VERSION,
        }
        data = self.query_wikijs(query)
        _ = xpath(data, 'data/pages/version')
        return PageVersion(api=self, page=page_history.page, **_)

    ##############################################

    def create_page(self, page: Page) -> ResponseResult:
        variables = {_: getattr(page, _) for _ in (
            'content',
            'description',
            'isPublished',
            'isPrivate',
            'locale',
            # 'path',
            'tags',
            'title',
        )}
        variables['path'] = page.path_str
        variables.update({
            'editor': page.contentType,
            'publishEndDate': '',
            'publishStartDate': '',
            'scriptCss': '',
            'scriptJs': '',
        })
        query = {
            'variables': variables,
            "query": Q.CREATE_PAGE,
        }
        # pprint(query)
        data = self.query_wikijs(query)
        # pprint(data)
        _ = xpath(data, 'data/pages/create/page')
        page.id = int(_['id'])
        page.createdAt = _['createdAt']
        page.updatedAt = _['updatedAt']
        _ = xpath(data, 'data/pages/create/responseResult')
        return ResponseResult(**_)

    ##############################################

    def update_page(self, page: Page) -> ResponseResult:
        # Fixme: checkConflicts
        # "variables":{"id":96,"checkoutDate":"2024-11-07T02:04:57.106Z"}
        # "query ($id: Int!, $checkoutDate: Date!) { pages {
        #   checkConflicts(id: $id, checkoutDate: $checkoutDate) }}"}]'
        # Fixme: ok ?
        if page.id is None:
            raise NameError(f"Cannot update a page without id")
        query = {
            'variables': {
                'id': page.id,
                'content': page.content,
                'description': '',
                'editor': 'markdown',
                'isPrivate': False,
                'isPublished': True,
                'locale': page.locale,
                'path': page.path_str,
                'publishEndDate': '',
                'publishStartDate': '',
                'scriptCss': '',
                'scriptJs': '',
                'tags': page.tags,
                'title': page.title,
            },
            "query": Q.UPDATE_PAGE,
        }
        # pprint(query)
        data = self.query_wikijs(query)
        # pprint(data)
        _ = xpath(data, 'data/pages/update/responseResult')
        return ResponseResult(**_)

    ##############################################

    def move_page(self, page: Page, path: str, locale: str = 'fr') -> ResponseResult:
        query = {
            'variables': {
                'id': page.id,
                'destinationPath': str(path),
                'destinationLocale': locale,
            },
            'query': Q.MOVE_PAGE,
        }
        # pprint(query)
        data = self.query_wikijs(query)
        # pprint(data)
        _ = xpath(data, 'data/pages/move/responseResult')
        return ResponseResult(**_)

    ############################################################################
    #
    # Pages
    #

    def list_pages(self, order_by: str = 'PATH', reverse: bool = False, limit: int = 0) -> Iterator[Page]:
        order_by_direction = 'DESC' if reverse else 'ASC'
        # Fixme: cannot pass PageOrderBy as string ???
        query = {
            'variables': {
                'limit': limit,
                # 'order_By': order_by,
                # 'orderByDirection': order_by_direction,
            },
            # eval(f'f"""{Q.LIST_PAGE}"""')
            'query': Q.LIST_PAGE(order_by, order_by_direction),
        }
        # pprint(query)
        data = self.query_wikijs(query)
        for _ in xpath(data, 'data/pages/list'):
            yield Page(api=self, **_)

    ##############################################

    def list_page_for_tags(self, tags: list[str], order_by: str = 'PATH', limit: int = 0) -> Iterator[Page]:
        query = {
            'variables': {
                'tags': list(tags),
                'limit': limit,
            },
            'query': Q.LIST_PAGE_FOR_TAGS(order_by),
        }
        data = self.query_wikijs(query)
        for _ in xpath(data, 'data/pages/list'):
            yield Page(api=self, **_)

    ##############################################

    def tree(self, path: str) -> Iterator[Page]:
        """List the pages and folders in the parent of the page at `path`.
        When `includeAncestors` is True, the parent directories are also listed.
        """
        # Fixme: wikijs uses parent
        path = self._to_path(path)
        query = {
            'variables': {
                'path': path,
                # 'parent': 3,
                'locale': 'fr'
            },
            # parent: Int
            'query': Q.TREE_PATH,
        }
        data = self.query_wikijs(query)
        for _ in xpath(data, 'data/pages/tree'):
            yield PageTreeItem(api=self, **_)

    @cache(cache_name='itree')
    # def itree(self, id: int) -> Iterator[Page]:
    def itree(self, id: int) -> list[Page]:
        """List the pages and folders in the parent of the page at `path`.
        When `includeAncestors` is True, the parent directories are also listed.
        """
        # Fixme: wikijs uses parent
        query = {
            'variables': {
                'parent': int(id),
                'locale': 'fr'
            },
            'query': Q.TREE_PARENT,
        }
        data = self.query_wikijs(query)
        # for _ in xpath(data, 'data/pages/tree'):
        #     yield PageTreeItem(api=self, **_)
        return [PageTreeItem(api=self, **_) for _ in xpath(data, 'data/pages/tree')]

    ##############################################

    def build_page_tree(self, progress_bar_cls) -> Node:
        # Runnning time is proportionnal to the number of pages
        root = Node()

        def process_page(page: Page) -> None:
            # print('-'*10)
            # print(f"@{page.locale} {page.path}")
            path = page.split_path
            parent = root
            # / dir1 / dir2 / ... / page
            for _ in path:
                try:
                    node = parent[_]
                except KeyError:
                    # add directory
                    node = Node(_)
                    node.page = None
                    parent.add_child(node)
                # print(f'{parent} // {node}')
                parent = node
            # parent is leaf
            parent.page = page

        pages = self.list_pages()
        if progress_bar_cls is not None:
            with progress_bar_cls() as pb:
                for page in pb(pages, total=self._number_of_pages):
                    process_page(page)
        else:
            for page in pages:
                process_page(page)

        return root

    ##############################################

    def search(self, query: str) -> PageSearchResponse:
        query = {
            'variables': {
                'query': query,
            },
            'query': Q.SEARCH_PAGE,
        }
        data = self.query_wikijs(query)
        results = [PageSearchResult(**_) for _ in xpath(data, 'data/pages/search/results')]
        _ = {
            key: value
            for key, value in xpath(data, 'data/pages/search').items()
            if key != 'results'
        }
        return PageSearchResponse(
            results=results,
            **_,
        )

    ##############################################

    def history(self, progress_callback, preload_version: bool = True) -> list[PageHistory]:
        # history = [_ for page in self.list_pages() for _ in page.history]
        history = []
        P_STEP = 10
        next_p = P_STEP
        for i, page in enumerate(self.list_pages()):
            p = 100 * i / self._number_of_pages
            if p > next_p:
                progress_callback(int(p))
                next_p += P_STEP
            print(f'{page.path}')
            for _ in page.history:
                if preload_version:
                    _.page_version
                history.append(_)
        history.sort(key=lambda _: _.date)
        # for _ in history:
        #     print(f'{_.versionId} {_.date} {_.page.id} {_.page.path} {_.actionType}')
        return history

    ############################################################################
    #
    # Tag
    #

    def tags(self) -> Iterator[Tag]:
        query = {
            'query': Q.TAGS,
        }
        data = self.query_wikijs(query)
        for _ in xpath(data, 'data/pages/tags'):
            yield Tag(**_)

    ##############################################

    def search_tags(self, query: str) -> list[str]:
        query = {
            'variables': {
                'query': query,
            },
            'query': Q.SEARCH_TAGS,
        }
        data = self.query_wikijs(query)
        return xpath(data, 'data/pages/searchTags')

    ############################################################################
    #
    # Asset
    #

    def list_asset_subfolder(self, folder_id: int = 0) -> Iterator[AssetFolder]:
        query = {
            'variables': {
                'parentFolderId': folder_id,
            },
            'query': Q.LIST_ASSET_SUBFOLDER,
        }
        data = self.query_wikijs(query)
        for _ in xpath(data, 'data/assets/folders'):
            yield AssetFolder(self, **_)

    ##############################################

    def build_asset_tree(self) -> Node:
        # We cannot implement a progress bar since we don't know the number of nodes.
        # A workaround would be to save the number of nodes in a config file.
        # And to use it for the next run.

        root = Node()

        def process_folder(parent: Node, folder_id: int) -> None:
            for _ in self.list_asset_subfolder(folder_id):
                node = Node(_.name)
                parent.add_child(node)
                process_folder(node, _.id)

        process_folder(root, 0)
        return root

    ##############################################

    def list_asset(self, folder_id: int) -> Iterator[Asset]:
        query = {
            'variables': {
                'folderId': folder_id,
                'kind': 'ALL',
            },
            'query': Q.LIST_ASSET,
            # folder: AssetFolder
            # author: Author
        }
        data = self.query_wikijs(query)
        for _ in xpath(data, 'data/assets/list'):
            yield Asset(**_)

    ############################################################################
    #
    #
    #

    def links(self) -> Iterator[PageLinkItem]:
        query = {
            'variables': {
                'locale': 'fr',
            },
            'query': Q.LINKS,
        }
        data = self.query_wikijs(query)
        # pprint(data)
        for _ in xpath(data, 'data/pages/links'):
            link = PageLinkItem(**_)
            if link.links:
                yield link
