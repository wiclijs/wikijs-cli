####################################################################################################
#
# wikijs-cli - A CLI for Wiki.js
# Copyright (C) 2025 Fabrice SALVAIRE
# SPDX-License-Identifier: GPL-3.0-or-later
#
####################################################################################################

# Fixme: we could extract common parts

####################################################################################################

import re
import os

from .printer import html_escape

LINESEP = os.linesep

####################################################################################################

def dump_query(query: dict, colourize: bool = True) -> str:
    variables = query.get('variables', {})
    # remove \n, multi-spaces, ensure space before }
    query_str = query['query']
    query_str = query_str.replace('\n', '')
    query_str = re.sub(' +', ' ', query_str)
    query_str = re.sub('([a-z])}', r'\1 }', query_str)

    if colourize:
        colour = 'blue'
        for c in '(){}:,$!':
            query_str = query_str.replace(c, f'<{colour}>{c}</{colour}>')

    # Fixme: html_escape / colourize
    variables = LINESEP.join([f'    {key}: {html_escape(value)}' for key, value in variables.items()])
    if variables:
        if colourize:
            colour = 'blue'
            for c in "{}:,'":
                variables = variables.replace(c, f'<{colour}>{c}</{colour}>')
            with_ = f"<{colour}>with</{colour}>"
        else:
            with_ = f"with"

        return f'"{query_str}"{LINESEP}  {with_}{LINESEP}{variables}'
    else:
        return query_str

####################################################################################################

def clean_query(query: str) -> str:
    cleaned = ''
    for line in query.splitlines():
        line = line.strip()
        if line.startswith('#'):
            continue
        if cleaned:
            cleaned += ' '
        cleaned += line

    # Check for unbalanced () {}
    in_parenthesis = 0
    in_brace = 0
    for c in cleaned:
        match c:
            case '(':
                in_parenthesis += 1
            case ')':
                in_parenthesis -= 1
            case '{':
                in_brace += 1
            case '}':
                in_brace -= 1
    if in_parenthesis != 0 or in_brace != 0:
        raise NameError(f'Query have unbalanced parenthesis {in_parenthesis} brace {in_brace}: {query}')

    return cleaned

####################################################################################################

INFO = '''
{
system {
  info {
    # SystemInfo
    #   partial
    currentVersion
    latestVersion
    groupsTotal
    pagesTotal
    usersTotal
    tagsTotal
}}}
'''

PAGE = '''
query ($path: String!, $locale: String!) {
  pages {
    singleByPath(path: $path, locale: $locale) {
      # Page
      id
      path
      hash
      title
      description
      isPrivate
      isPublished
      privateNS
      publishStartDate
      publishEndDate
      tags {
        # PageTag
        tag
      }
      # content
      render
      # toc # Error: String cannot represent value
      contentType
      createdAt
      updatedAt
      editor
      locale
      scriptCss
      scriptJs
      authorId
      authorName
      authorEmail
      creatorId
      creatorName
      creatorEmail
}}}
'''

# query ($limit: Int!, $orderBy: PageOrderBy!, $orderByDirection: PageOrderByDirection!) {
#     list(limit: $limit, orderBy: $orderBy, orderByDirection: $orderByDirection) {
def LIST_PAGE(order_by, order_by_direction):
    return f'''
query ($limit: Int!) {{
  pages {{
    list(
      limit: $limit,
      orderBy: {order_by},
      orderByDirection: {order_by_direction}
    ) {{
      # PageListItem
      id
      path
      locale
      title
      description
      contentType
      isPublished
      isPrivate
      privateNS
      createdAt
      updatedAt
      tags
}}}}}}
'''

def LIST_PAGE_FOR_TAGS(order_by):
    return f'''
query ($tags: [String!], $limit: Int!) {{
  pages {{
    list(
      limit: $limit,
      orderBy: {order_by},
      tags: $tags
    ) {{
      # PageListItem
      id
      path
      locale
      title
      description
      contentType
      isPublished
      isPrivate
      privateNS
      createdAt
      updatedAt
      tags
}}}}}}
'''

TREE_PATH = '''
query ($path: String!, $locale: String!) {
  pages {
    tree(path: $path, mode: ALL, locale: $locale, includeAncestors: false) {
      # PageTreeItem
      id
      path
      depth
      title
      isPrivate
      isFolder
      privateNS
      parent
      pageId
      locale
}}}
'''

TREE_PARENT = '''
query ($parent: Int, $locale: String!) {
  pages {
    tree(parent: $parent, mode: ALL, locale: $locale, includeAncestors: false) {
      # PageTreeItem
      id
      path
      depth
      title
      isPrivate
      isFolder
      privateNS
      parent
      pageId
      locale
}}}
'''

PAGE_HISTORY = '''
query ($id: Int!) {
  pages {
    history(id: $id) {
      # PageHistoryResult
      trail {
        # PageHistory
        versionId
        versionDate
        authorId
        authorName
        actionType
        valueBefore
        valueAfter
      }
      total
}}}
'''

LIST_ASSET_SUBFOLDER = '''
query ($parentFolderId: Int!) {
  assets {
    folders(parentFolderId: $parentFolderId) {
      # AssetFolder
      id
      name
      slug
}}}
'''

LIST_ASSET = '''
query ($folderId: Int!, $kind: AssetKind!) {
  assets {
    list(folderId: $folderId, kind: $kind) {
      # AssetItem
      id
      filename
      ext
      kind
      mime
      fileSize
      metadata
      createdAt
      updatedAt
      # folder: AssetFolder
      # author
}}}
'''

PAGE_VERSION = '''
query ($id: Int!, $version_id: Int!) {
  pages {
    version(pageId: $id, versionId: $version_id) {
      # PageVersion
      action
      authorId
      authorName
      content
      contentType
      createdAt
      versionDate
      description
      editor
      isPrivate
      isPublished
      locale
      pageId
      path
      publishEndDate
      publishStartDate
      tags
      title
      versionId
}}}
'''

MOVE_PAGE = '''
mutation ($id: Int!, $destinationPath: String!, $destinationLocale: String!) {
  pages {
    move(id: $id, destinationPath: $destinationPath, destinationLocale: $destinationLocale) {
      responseResult {
        # ResponseStatus
        succeeded
        errorCode
        slug
        message
      }
}}}
'''

CREATE_PAGE = '''
mutation (
  $content: String!,
  $description: String!,
  $editor: String!,
  $isPrivate: Boolean!,
  $isPublished: Boolean!,
  $locale: String!,
  $path: String!,
  $publishEndDate: Date,
  $publishStartDate: Date,
  $scriptCss: String,
  $scriptJs: String,
  $tags: [String]!,
  $title: String!
) {
  pages {
    create(
      # PageMutation
      content: $content,
      description: $description,
      editor: $editor,
      isPrivate: $isPrivate,
      isPublished: $isPublished,
      locale: $locale,
      path: $path,
      publishEndDate: $publishEndDate,
      publishStartDate: $publishStartDate,
      scriptCss: $scriptCss,
      scriptJs: $scriptJs,
      tags: $tags,
      title: $title
    ) {
      responseResult {
        succeeded
        errorCode
        slug
        message
      }
      page {
        id
        createdAt
        updatedAt
      }
}}}
'''

UPDATE_PAGE = '''
mutation ($id: Int!,
   $content: String,
   $description: String,
   $editor: String,
   $isPrivate: Boolean,
   $isPublished: Boolean,
   $locale: String,
   $path: String,
   $publishEndDate: Date,
   $publishStartDate: Date,
   $scriptCss: String,
   $scriptJs: String,
   $tags: [String],
   $title: String) {
  pages {
    update(
      # PageMutation
      id: $id,
      content: $content,
      description: $description,
      editor: $editor,
      isPrivate: $isPrivate,
      isPublished: $isPublished,
      locale: $locale,
      path: $path,
      publishEndDate: $publishEndDate,
      publishStartDate: $publishStartDate,
      scriptCss: $scriptCss,
      scriptJs: $scriptJs,
      tags: $tags,
      title: $title
    ) {
      responseResult {
        succeeded
        errorCode
        slug
        message
      }
      page {
        updatedAt
      }
}}}
'''

PAGE_SEARCH = '''
query ($query: String!) {
  pages {
    search(query: $query) {
      # PageSearchResponse
      results {
        # PageSearchResult
        id
        title
        description
        path
        locale
      }
      suggestions
      totalHits
}}}
'''

TAGS = '''
{
  pages {
    tags {
      # PageTag
      id
      tag
      title
      createdAt
      updatedAt
}}}
'''

SEARCH_TAGS = '''
query ($query: String!) {
  pages {
    searchTags(query: $query)
}}
'''

LINKS = '''
query ($locale: String!) {
  pages {
    links(locale: $locale) {
      # PageLinkItem
      id
      path
      title
      links
}}}
'''
