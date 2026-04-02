####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['Node']

####################################################################################################

from collections.abc import Iterator
from pathlib import PurePosixPath

from .unicode import usorted

####################################################################################################

class Node:

    ##############################################

    def __init__(self, name: str = '') -> None:
        self._name = str(name)
        self._parent: Node | None = None
        self._childs: dict[str, Node] = {}

    ##############################################

    def __str__(self) -> str:
        return self._name

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> PurePosixPath:
        if self.is_root:
            return PurePosixPath('/')
        # Fixme: ty doesn't understand is_root
        elif self.parent.is_root:  # ty:ignore[unresolved-attribute]
            return PurePosixPath('/', self._name)
        else:
            return self.parent.path.joinpath(self._name)  # ty:ignore[unresolved-attribute]

    @property
    def is_root(self) -> bool:
        return self._parent is None

    @property
    def is_folder(self) -> bool:
        return bool(self._childs)

    @property
    def is_leaf(self) -> bool:
        return not self._childs

    @property
    def parent(self) -> type['Node'] | None:
        return self._parent

    @parent.setter
    def parent(self, node: 'Node') -> None:
        self._parent = node

    @property
    def childs(self) -> Iterator['Node']:
        childs = list(self._childs.values())
        # childs.sort(key=lambda _: _._name)
        childs = usorted(childs, 'name')  # ty:ignore[invalid-argument-type]
        return iter(childs)

    @property
    def folder_childs(self) -> Iterator['Node']:
        for _ in self.childs:
            if _.is_folder:
                yield _

    @property
    def leaf_childs(self) -> Iterator['Node']:
        for _ in self.childs:
            if _.is_leaf:
                yield _

    @property
    def child_names(self) -> list[str]:
        return usorted(self._childs.keys())  # ty:ignore[invalid-argument-type]

    @property
    def folder_names(self) -> list[str]:
        return usorted([_.name for _ in self.folder_childs])

    @property
    def leaf_names(self) -> list[str]:
        return usorted([_.name for _ in self.leaf_childs])

    ##############################################

    def add_child(self, child: 'Node') -> None:
        if child.name not in self._childs:
            self._childs[child.name] = child
            child.parent = self

    ##############################################

    def __getitem__(self, name: str) -> 'Node':
        return self._childs[name]

    def __contains__(self, name: str) -> bool:
        return name in self._childs

    ##############################################

    def _find_impl(self, path: list[str]) -> 'Node':
        if path:
            _ = path.pop()
            if _ in self:
                return self[_]._find_impl(path)
        #     else:
        #         return self
        # else:
        return self

    def find(self, path: str) -> 'Node':
        it = reversed(str(path).split('/'))
        path_ = list(filter(bool, it))
        return self._find_impl(path_)

    ##############################################

    def join(self, path: str) -> str:
        if self.is_root:
            return f'/{path}'
        else:
            return f'{self.path}/{path}'
