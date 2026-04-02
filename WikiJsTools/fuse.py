####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

####################################################################################################
#
# Emacs : (setq create-lockfiles nil)
#
# Somebody scans the whole file hierarchy
# Dolphin calls getxattr
# Editors attempt to write and read a lot of backup files...
#
####################################################################################################

####################################################################################################

__all__ = ['mount']

####################################################################################################

# import logging

from collections import defaultdict
from collections.abc import Iterable
from errno import ENOENT
from pathlib import PurePosixPath
from stat import S_IFDIR, S_IFREG
from time import time
from typing import Any
import ctypes
import logging
import os

# https://github.com/mxmlnkn/mfusepy
import mfusepy as fuse

from .WikiJsApi import WikiJsApi, Page

####################################################################################################

LINESEP = os.linesep

_module_logger = logging.getLogger(__name__)

####################################################################################################

def mount(api: WikiJsApi, path: str) -> None:
    fuse.FUSE(WikiJsFuse(api), path, foreground=True, allow_other=True)

####################################################################################################

def ensure_buffer_size(data: bytes, length: int) -> bytes:
    """Truncate data to length and fill with zero bytes if necessary"""
    if length < 0:
        raise ValueError("Negative length")
    elif length == 0:
        return b''
    else:
        return data[:length].ljust(length, '\x00'.encode('ascii'))

####################################################################################################

class VirtualDirectory:

    _logger = _module_logger.getChild('VirtualDirectory')

    ##############################################

    def __init__(self, wfuse: 'WikiJsFuse', path: str, mode: int=0o755) -> None:
        self._wfuse = wfuse
        path = str(path)
        self._path = PurePosixPath(path)
        # self._fd = int(fd)

        # now = time()
        now = self._wfuse._mount_time
        self._stat = dict(
            st_mode=(S_IFDIR | mode),
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            st_nlink=2,
        )

    ##############################################

    # @property
    # def fd(self) -> int:
    #     return self._fd

    @property
    def path(self) -> PurePosixPath:
        return self._path

    @property
    def path_str(self) -> str:
        return str(self._path)

    @property
    def stat(self) -> dict:
        return self._stat

####################################################################################################

class VirtualFile:

    _logger = _module_logger.getChild('VirtualFile')

    ##############################################

    def __init__(self, wfuse: 'WikiJsFuse', path: str, fd: int, create: bool, mode: int = 0o644) -> None:
        self._wfuse = wfuse
        path = str(path)
        self._path = PurePosixPath(path)
        self._fd = int(fd)
        self._created = create
        self._page: Page | None = None
        self._data = b''
        self._write_pending = False
        if not create:
            self._page = self._wfuse._api.page(path)
            self._stat = self.page_stat(self._page)
            self._data = self._page.bytes_data
        else:
            # self._page = None
            # self._data = b''
            now = time()
            self._stat = dict(
                st_mode=(S_IFREG | mode),
                st_ctime=now,
                st_mtime=now,
                st_atime=now,
                st_nlink=1,
                st_size=0,
            )

    ##############################################

    @classmethod
    def page_stat(self, page) -> dict[str, Any]:
        return dict(
            st_mode=(S_IFREG | 0o644),   # Fixme: mode
            st_ctime=page.created_at.timestamp(),
            st_mtime=page.updated_at.timestamp(),
            # st_atime=mount_time,
            st_atime=time(),
            st_nlink=1,
            st_size=page.bytes_size,
        )

    ##############################################

    @property
    def _api(self) -> WikiJsApi:
        return self._wfuse._api

    @property
    def created(self) -> bool:
        return self._created

    @property
    def is_page(self) -> bool:
        return hasattr(self, '_page')

    @property
    def fd(self) -> int:
        return self._fd

    @property
    def path(self) -> PurePosixPath:
        return self._path

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def path_str(self) -> str:
        return str(self._path)

    @property
    def stat(self) -> dict:
        return self._stat

    @property
    def data(self) -> bytes:
        # if self.is_page:
        #     return self._page.bytes_data
        # else:
        return self._data

    ##############################################

    @property
    def is_wiki_page(self) -> bool:
        if self._page is not None:
            return True
        filename = self.name
        if filename[0] in '.#' or filename[-1] in '~#':
            return False
        return self._data.startswith(b'title:')

    ##############################################

    def read(self, size: int, offset: int) -> bytes:
        return self.data[offset:offset + size]

    ##############################################

    def truncate(self, length: int) -> None:
        #! self._logger.info(f"truncate '{self.path_str}' {length}")
        # make sure extending the file fills in zero bytes
        self._data = ensure_buffer_size(self._data, length)
        self._stat['st_size'] = length

    ##############################################

    def write(self, data: bytes, offset: int) -> int:
        # write is buffered by 4096, last chunk can be < 4096
        # sequence:
        #   getattr '/Test/long-page' fd=None
        #   create '/Test/long-page' mode=33204 fi=33345
        #   getattr '/Test/long-page' fd=1
        #   getxattr '/Test/long-page' name=security.capability position=0
        #   Write '/Test/long-page' offset=0 size=4096 fd=1
        #   Write '/Test/long-page' offset=4096 size=4096 fd=1
        #   ...
        #   Write '/Test/long-page' offset=176128 size=1986 fd=1
        #   getattr '/Test/long-page' fd=None
        #   release '/Test/long-page' fd=1
        #! self._logger.info(f"write '{self.path_str}' @{offset} s={len(data)}")
        # Write can be incomplete !!!
        # make sure the data gets inserted at the right offset
        # and only overwrites the bytes that data is replacing
        file_data = self._data
        head = ensure_buffer_size(file_data, offset)
        tail = file_data[offset + len(data):]
        # print(head)
        # print(data)
        # print(tail)
        self._data = head + data + tail
        if self.is_wiki_page:
            self._logger.info(f"Append wiki page {self.path_str} offset={offset} size={len(data)}")
            self._write_pending = True
        else:
            self._logger.info(f"Write virtual file '{self.path_str}'")
            self._stat['st_size'] = len(self._data)
        return len(data)

    ##############################################

    def release(self) -> None:
        if not (self.is_wiki_page and self._write_pending):
            return
        udata = self._data.decode('utf8')
        RULE = '~'*100
        CHUNK_SIZE = 256
        if len(udata) > (CHUNK_SIZE * 2 + 64):
            _ = LINESEP.join((udata[:CHUNK_SIZE], '... TRUNCATED ...', udata[-CHUNK_SIZE:]))
        else:
            _ = udata
        _ = LINESEP.join(('', RULE, _, RULE))
        self._logger.info(f"Write on wiki {self.path_str}{_}")
        # Fixme: generate path
        page = Page.import_(udata, self._api)
        # Fixme: check path match
        if page.id is not None:
            page.update()
        else:
            page.create()
        self._page = page
        self._stat = self.page_stat(page)

####################################################################################################

# Use log_callback instead of LoggingMixIn !
class WikiJsFuse(fuse.LoggingMixIn, fuse.Operations):

    # https://libfuse.github.io/doxygen/structfuse__operations.html

    _logger = _module_logger.getChild('WikiJsFuse')

    ##############################################

    def __init__(self, api: WikiJsApi) -> None:
        self._api = api
        self._mount_time = time()
        self._file_by_path: dict[str, VirtualDirectory | VirtualFile] = {
            '/': VirtualDirectory(self, '/')
        }
        self._file_by_fd: dict[int, VirtualFile] = {}
        self._last_fd = 0
        # Fixme:
        self.data = defaultdict(str)
        # now = time()
        # self._files['/'] = dict(
        #     st_mode=(S_IFDIR | 0o755),
        #     st_ctime=now,
        #     st_mtime=now,
        #     st_atime=now,
        #     st_nlink=2,
        # )

    ##############################################

    def new_fd(self, path: str, create: bool) -> VirtualFile:
        self._last_fd += 1
        file = VirtualFile(self, path, self._last_fd, create)
        self._file_by_path[file.path_str] = file
        self._file_by_fd[file.fd] = file
        return file

    ##############################################

    # def _list_folder(self, path: str) -> None:
    #     items = list(self._itree(0))
    #     for item in items:
    #         print(item.id, item.path, item.isFolder)

    def _query_folder(self, path: PurePosixPath) -> list[dict]:
        cache = []
        for i, part in enumerate(path.parts):
            if i == 0:
                folder_id = 0
            else:
                folder = cache[i-1][part]
                folder_id = folder.id
            items = {_.path.name: _ for _ in self._api.itree(folder_id)}
            cache.append(items)
        return cache

    ##############################################

    @fuse.overrides(fuse.Operations)
    def chmod(self, path: str, mode: int) -> int:
        self._logger.debug(f"chmod '{path}' mode={mode}")
        # self._files[path]['st_mode'] &= 0o770000
        # self._files[path]['st_mode'] |= mode
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def chown(self, path: str, uid: int, gid: int) -> int:
        self._logger.debug(f"chmod '{path}' uid={uid} gid={gid}")
        # self._files[path]['st_uid'] = uid
        # self._files[path]['st_gid'] = gid
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def create(self, path: str, mode: int, fi=None) -> int:
        self._logger.info(f"create '{path}' mode={mode} fi={fi}")
        # uid, gid, _pid = fuse.fuse_get_context()
        file = self.new_fd(path, create=True)
        return file.fd

    ##############################################

    @fuse.overrides(fuse.Operations)
    def getattr(self, path: str, fd=None) -> dict[str, Any]:
        """Get file attributes. Similar to stat()"""
        self._logger.info(f"getattr '{path}' fd={fd}")
        # if path not in self._files:
        #     raise FuseOSError(ENOENT)
        # return self._files[path]
        if fd is not None:
            return self._file_by_fd[fd].stat

        mount_time = self._mount_time
        if path in self._file_by_path:
            return self._file_by_path[path].stat
        else:
            opath = PurePosixPath(path)
            try:
                cache = self._query_folder(opath.parent)
                # print(f"Lookup {path}")
                # print(f"Cache {cache[-1]}")
                item = cache[-1][opath.name]
            except KeyError:
                raise fuse.FuseOSError(ENOENT)
            if item.isFolder:
                return dict(
                    st_mode=(S_IFDIR | 0o755),
                    st_ctime=mount_time,
                    st_mtime=mount_time,
                    st_atime=mount_time,
                    st_nlink=2,
                )
            else:
                page = self._api.page(path)
                return VirtualFile.page_stat(page)

    ##############################################

    @fuse.overrides(fuse.Operations)
    def getxattr(self, path: str, name: str, position: int = 0) -> bytes:
        self._logger.info(f"getxattr '{path}' name={name} position={position}")
        # attrs = self._files[path].get('attrs', {})
        # try:
        #     return attrs[name]
        # except KeyError:
        #     return ''   # Should return ENOATTR
        # match name:
        #     case 'system.posix_acl_access':
        #     case 'security.capability'
        #         # return 'unconfined_u:object_r:user_home_t:s0'
        #         return FuseOSError(ENODATA)
        # return FuseOSError(ENODATA)
        return b''

    ##############################################

    @fuse.overrides(fuse.Operations)
    def listxattr(self, path: str) -> Iterable[str]:
        self._logger.info(f"listxattr '{path}'")
        # attrs = self._files[path].get('attrs', {})
        # return attrs.keys()
        return ()

    ##############################################

    @fuse.overrides(fuse.Operations)
    def mkdir(self, path: str, mode: int) -> int:
        self._logger.info(f"mkdir '{path}' mode={mode}")
        directory = VirtualDirectory(self, path, mode)
        self._file_by_path[path] = directory
        try:
            parent = self._file_by_path[str(directory.path.parent)]
            parent.stat['st_nlink'] += 1
        except KeyError:
            # Fixme: wiki folder
            pass
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def open(self, path: str, flags: int) -> int:
        # OpenBSD calls mknod + open instead of create.
        # See create
        self._logger.info(f"open '{path}' flags={flags}")
        file = self._file_by_path.get(path, None)
        if file is None:
            file = self.new_fd(path, create=False)
        return file.fd  # ty:ignore[unresolved-attribute]

    ##############################################

    @fuse.overrides(fuse.Operations)
    def read(self, path: str, size: int, offset: int, fd: int) -> bytes:
        self._logger.info(f"read '{path}' size={size} offset={offset} fd={fd}")
        file = self._file_by_fd[fd]
        return file.read(size, offset)

    ##############################################

    @fuse.overrides(fuse.Operations)
    def readdir(self, path: str, fd: int) -> fuse.ReadDirResult:
        self._logger.info(f"readdir '{path}' fd={fd}")
        opath = PurePosixPath(path)
        in_memory_file = []
        for file in self._file_by_path.values():
            fpath = file.path
            if file.path_str == '/':
                continue
            if (isinstance(file, VirtualDirectory) or file.created) and fpath.parent == opath:
                in_memory_file.append(fpath.name)
        entries = ['.', '..'] + in_memory_file
        try:
            cache = self._query_folder(opath)
            entries += list(cache[-1].keys())
        except KeyError:
            pass
        # print(entries)
        return entries

    ##############################################

    @fuse.overrides(fuse.Operations)
    def readlink(self, path: str) -> str:
        self._logger.info(f"readlink '{path}'")
        return self.data[path]

    ##############################################

    @fuse.overrides(fuse.Operations)
    def release(self, path: str, fd: int) -> int:
        self._logger.debug(f"release '{path}' fd={fd}")
        file = self._file_by_fd[fd]
        file.release()
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def removexattr(self, path: str, name) -> int:
        self._logger.info(f"removexattr '{path}' name={name}")
        # attrs = self._files[path].get('attrs', {})
        # try:
        #     del attrs[name]
        # except KeyError:
        #     pass   # Should return ENOATTR
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def rename(self, old: str, new: str) -> int:
        self._logger.info(f"rename '{old}' -> '{new}'")
        # self.data[new] = self.data.pop(old)
        # self._files[new] = self._files.pop(old)
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def rmdir(self, path: str) -> int:
        self._logger.info(f"rmdir '{path}'")
        # with multiple level support, need to raise ENOTEMPTY if contains any files
        # self._files.pop(path)
        # self._files['/']['st_nlink'] -= 1
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def setxattr(self, path: str, name: str, value, options: int, position: int = 0) -> int:
        self._logger.info(f"setxattr '{path}' name={name} value={value} options={options} position={position}")
        # Ignore options
        # attrs = self._files[path].setdefault('attrs', {})
        # attrs[name] = value
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def statfs(self, path: str) -> dict[str, int]:
        self._logger.info(f"statfs '{path}'")
        return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)

    ##############################################

    @fuse.overrides(fuse.Operations)
    def symlink(self, target: str, source: str) -> int:
        # Fixme: Emacs create symlinks...
        self._logger.info(f"symlink '{target}' -> '{source}'")
        # self._files[target] = dict(
        #     st_mode=(S_IFLNK | 0o777),
        #     st_nlink=1,
        #     st_size=len(source),
        # )
        # self.data[target] = source
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def truncate(self, path: str, length: int, fd=None) -> int:
        self._logger.info(f"truncate '{path}' length={length} fd={fd}")
        if fd is not None:
            file = self._file_by_fd[fd]
        else:
            file = self._file_by_path[path]
        file.truncate(length)  # ty:ignore[unresolved-attribute]
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def unlink(self, path: str) -> int:
        self._logger.info(f"unlink '{path}'")
        # self._file_by_path.pop(path)
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def utimens(self, path: str, times: tuple[int, int] | None = None) -> int:
        self._logger.info(f"utimens '{path}' times={times}")
        # now = time()
        # atime, mtime = times if times else (now, now)
        # self._files[path]['st_atime'] = atime
        # self._files[path]['st_mtime'] = mtime
        return 0

    ##############################################

    @fuse.overrides(fuse.Operations)
    def write(self, path: str, data: bytes, offset: int, fd: int) -> int:
        # self._logger.debug(f"Write '{path}' offset={offset} fd={fd} data={data}")
        self._logger.info(f"Write '{path}' offset={offset} size={len(data)} fd={fd}")
        file = self._file_by_fd[fd]
        return file.write(data, offset)

    ##############################################

    @fuse.overrides(fuse.Operations)
    def mknod(self, path: str, mode: int, dev: int) -> int:
        # OpenBSD calls mknod + open instead of create.
        self._logger.debug(f"wmknod '{path}' mode={mode} dev={dev}")
        return 0

    @fuse.overrides(fuse.Operations)
    def ioctl(self, path: str, cmd: int, arg: ctypes.c_void_p, fd: int, flags: int, data: ctypes.c_void_p) -> int:
        self._logger.debug(f"ioctl '{path}' cmd={cmd} arg={arg} fd={fd} flags={flags} data={data}")
        return 0
