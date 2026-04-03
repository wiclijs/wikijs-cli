####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

__all__ = ['sync', 'git_sync']

####################################################################################################

import json  # noqa: I001
import os
import subprocess
from datetime import datetime
from pathlib import Path
# from pprint import pprint
from typing import cast

from .printer import CommandError, init_console
from .WikiJsApi import WikiJsApi

####################################################################################################

GIT = '/usr/bin/git'

HISTORY_JSON = 'wikijs-history.json'

####################################################################################################

def git(repo_path, command: str, *args, **kwargs) -> str | None:
    console = init_console()
    printc = console.print
    args = [str(_) for _ in args]
    cmd = (
        GIT,
        '--no-pager',
        command,
        *args,
    )
    _ = ' '.join(cmd)
    printc(f"Run {_}")
    capture_output = kwargs.get('capture_output', False)
    process = subprocess.run(
        cmd,
        check=True,
        cwd=repo_path,
        capture_output=capture_output,
    )
    if capture_output and process.stdout is not None:
        # print(process.stderr, process.stdout)
        return process.stdout.decode('utf8')
    return None


def get_last_commit_date(repo_path) -> datetime:
    output = git(repo_path, 'log', '-1', '--date=iso-strict', '--format="%ad"', capture_output=True)
    if output is not None:
        return datetime.fromisoformat(output.strip().replace('"', ''))
    else:
        raise ValueError("Git returned None")

####################################################################################################

def sync_asset(api: WikiJsApi, path: Path, exist_ok: bool = False) -> None:

    # DANGER : remove all the files that are not listed as assets !!!

    console = init_console()
    printc = console.print

    asset_path = Path(path).expanduser().resolve()
    printc(f"<blue>Sync asset path</blue> <green>{asset_path}</green>")

    # Protection
    if asset_path.exists() and not exist_ok:
        raise CommandError(f"<red>Asset path <green>{asset_path}</green> exists</red>")
    asset_path.mkdir(parents=True, exist_ok=exist_ok)

    # Collect current asset list on disk
    paths = []
    for dirpath, _, filenames in asset_path.walk():
        dirpath = Path(dirpath)
        for filename in filenames:
            _ = dirpath.joinpath(filename)
            paths.append(_)

    def process_folder(folder_id: int = 0, stack: list | None = None):
        if stack is None:
            stack = []
        for asset in api.list_asset(folder_id):
            # url = '/'.join([api.api_url] + stack + [asset.filename])
            asset.path = '/'.join(stack + [asset.filename])
            yield asset
        for _ in api.list_asset_subfolder(folder_id):
            yield from process_folder(_.id, stack + [_.name])

    # To Git add, we must sort by date
    for asset in process_folder():
        data = api.get(asset.path)
        path = asset_path.joinpath(asset.path)   # .split('/')
        if path in paths:
            paths.remove(path)
        # asset.created_at.timestamp()
        mtime = asset.updated_at.timestamp()
        if not (path.exists() and path.stat().st_mtime == mtime):
            printc(f"Write <green>{asset.path}</green>")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            os.utime(path, (mtime, mtime))

    # Clean old assets
    for _ in paths:
        _.unlink()

####################################################################################################

def sync(api: WikiJsApi, path: Path) -> None:
    """Sync on disk"""

    # DANGER : write many files and delete old assets !!!

    console = init_console()
    printc = console.print

    sync_path = Path(path).expanduser().resolve()
    if sync_path.exists():
        raise CommandError(f"<red>Sync path <green>{sync_path}</green> exists</red>")
    printc(f"<blue>Sync path</blue> <green>{sync_path}</green>")
    # Protection
    sync_path.mkdir(exist_ok=False)

    for page in api.list_pages():
        # page.complete()
        file_path = page.sync(sync_path)
        if file_path is not None:
            _ = file_path.relative_to(sync_path)
            printc(f"Wrote <green>{_}</green>")
        # else is up to date

    asset_path = sync_path.joinpath('_assets')
    sync_asset(api, asset_path)

####################################################################################################

def git_sync(api: WikiJsApi, path: Path) -> None:
    """Sync Git repo"""

    # DANGER : don't run in another Git repo !!!

    # Fixme: remove ???
    # Protection
    # if Path.cwd().joinpath('.git').exists():
    #     printc(f"Current path is a git repo. Exit")
    #     return

    console = init_console()
    printc = console.print

    repo_path = Path(path).expanduser().resolve()
    printc(f"<blue>Git repository path</blue> <green>{repo_path}</green>")

    created = False
    if repo_path.exists():
        # Protection
        if not repo_path.joinpath('.git').exists():
            raise CommandError(f"<red> Directory <green>{repo_path}</green> is not a git repository</red>")
        if not repo_path.joinpath(HISTORY_JSON).exists():
            raise CommandError(f"<red> Directory <green>{repo_path}</green> doesn't have a JSON history</red>")
        printc("<blue>Git already initialised</blue>")
    else:
        repo_path.mkdir()
        created = True

    history_json_path = repo_path.joinpath(HISTORY_JSON)
    asset_path = repo_path.joinpath('_assets')

    def git_(command: str, *args) -> None:
        git(repo_path, command, *args)

    def commit(date: datetime, message: str) -> None:
        git_(
            'commit',
            '-m', message,
            f'--date={date.isoformat()}',
        )

    json_versions = []  # Fixme: ty: unused
    last_version_date: datetime | None = None  # Fixme: this is not the last edit
    last_commit_date: datetime | None = None  # Fixme: ty: unused
    if created:
        git_('init')
    else:
        with open(history_json_path) as fh:
            json_versions = json.load(fh)
            last_version = json_versions[-1]
            # How versionID are generated ???
            # last_version_id = last_version['versionId']
            last_version_date = datetime.fromisoformat(last_version['versionDate'])
        printc(f"Last version date <blue>{last_version_date}</blue>")
        last_commit_date = get_last_commit_date(repo_path)
        printc(f"Last commit date <blue>{last_commit_date}</blue>")

    # Fixme: progress callback
    #  how to get number of versions ?
    def progress_callback(p: int) -> None:
        printc(f"<blue>{p} % done</blue>")

    # Fixme: skip ?
    printc("<blue>Get page histories...</blue>")
    history = api.history(progress_callback)
    printc("<blue>...Done</blue>")

    # Commit page history
    for ph in history:
        # Git commit date is limited to s and not ms !
        # if last_commit_date is not None and ph.date <= last_commit_date:
        if last_version_date is not None and ph.date <= last_version_date:
            continue

        page = ph.page

        is_moved = ph.is_moved
        if is_moved:
            old_upath, new_upath = cast(tuple[str, str], is_moved)
            printc(f'<blue>moved</blue> @{page.locale} "<green>{old_upath}</green>" -> "<green>{new_upath}</green>"')
            # Fixme: f'{ph.date_utc_str} <blue>move</blue> @{page.locale} {ph.old_path} -> {ph.new_path}'
            old_path = page.file_path(repo_path, old_upath)
            if old_path.exists():
                new_path = page.file_path(repo_path, new_upath)
                new_path.parent.mkdir(parents=True, exist_ok=True)
                # Fixme: remove old directory
                git_('mv', old_path, new_path)
                # update file content metadata
                # Fixme: file_path == new_path
                file_path = ph.sync(repo_path, check_exists=False)
                git_('add', file_path)
                # Fixme: is move and update possible ???
                message = f'move @{page.locale} "{ph.old_path}" -> "{ph.new_path}"'
                commit(ph.date, message)
            else:
                raise CommandError(f"<red>Error <green>{old_upath}</green> is missing</red>")
        else:
            if ph.is_initial:
                action = 'create'
            elif ph.is_edited:
                action = 'edit'
            elif ph.is_metadata_edited:
                action = 'metadata edit'
            else:
                action = 'ghost'
            printc(f'{ph.date_utc_str} <blue>{action}</blue> @{page.locale} <green>{page.path}</green>')
            file_path = ph.sync(repo_path, check_exists=False)
            git_('add', file_path)
            message = f'{action} @{page.locale} {page.path}'
            commit(ph.date, message)

    # Fixme: remove empty directory

    # Save Assets
    #  Wiki.js doesn't implement an history for assets
    #  so we rewrite...
    sync_asset(api, asset_path, exist_ok=True)

    printc("<blue>Clean old path</blue>")
    for root, direnames, _ in repo_path.walk():
        if root == repo_path:
            direnames.remove('.git')
        path = root
        while True:
            if list(path.iterdir()):   # Fixme: better ? next()
                break
            else:
                _ = path.relative_to(repo_path)
                printc(f"<green>{_}</green> <orange>is empty</orange>")
                path.rmdir()
                path = path.parent  # Fixme: ty

    # Now write history.json
    with open(history_json_path, 'w') as fh:
        # Fixme: reset ?
        json_versions = []
        for ph in history:
            # Fixme: better ?
            d = {
                key: value
                for key, value in ph.__dict__.items()
                if key not in ('api', 'page', '_page_version', 'prev', 'next') and value is not None
            }
            d['locale'] = ph.locale
            d['path'] = ph.path_str
            d['pageId'] = ph.page_id
            json_versions.append(d)
        # last = history[-1]
        # data = {
        #     'versions': versions,
        #     'last_version_id': last.versionId,
        #     'laste_date': last.versionDate,
        # }
        json.dump(json_versions, fh, ensure_ascii=False, indent=4)
