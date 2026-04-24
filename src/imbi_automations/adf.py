"""Atlassian Document Format (ADF) models and conversion."""

import html.parser
import re
import typing

import markdown
import pydantic


class Mark(pydantic.BaseModel):
    """An ADF inline mark (bold, italic, link, etc.).

    Attributes:
        type: Mark type (e.g., ``'strong'``, ``'em'``, ``'link'``)
        attrs: Optional attributes for the mark
    """

    type: str
    attrs: dict[str, typing.Any] | None = None


class InlineNode(pydantic.BaseModel):
    """An ADF inline node such as text or hardBreak.

    Attributes:
        type: Node type (e.g., ``'text'``, ``'hardBreak'``)
        text: Text content (required for ``'text'`` nodes)
        marks: Optional inline marks applied to this node
        attrs: Optional node attributes
    """

    type: str
    text: str | None = None
    marks: list[Mark] | None = None
    attrs: dict[str, typing.Any] | None = None


class BlockNode(pydantic.BaseModel):
    """An ADF block-level node (paragraph, heading, list, etc.).

    Attributes:
        type: Node type (e.g., ``'paragraph'``, ``'heading'``)
        content: Child nodes (inline or nested block nodes)
        attrs: Optional node attributes
    """

    type: str
    content: list[BlockNode | InlineNode] | None = None
    attrs: dict[str, typing.Any] | None = None


class Document(pydantic.BaseModel):
    """An ADF document.

    This is the top-level container for Atlassian Document Format
    content, used by Jira and Confluence APIs.

    Attributes:
        type: Always ``'doc'``
        version: ADF version, always ``1``
        content: Top-level block nodes
    """

    type: typing.Literal['doc'] = 'doc'
    version: typing.Literal[1] = 1
    content: list[BlockNode] = pydantic.Field(default_factory=list)


def markdown_to_adf(text: str) -> dict[str, typing.Any]:
    """Convert markdown text to an ADF document.

    Args:
        text: Markdown-formatted text

    Returns:
        ADF document dict with type='doc' and version=1
    """
    if not text.strip():
        return {
            'type': 'doc',
            'version': 1,
            'content': [{'type': 'paragraph', 'content': []}],
        }
    html_text = markdown.markdown(text, extensions=['fenced_code', 'tables'])
    parser = _HTMLToADFParser()
    parser.feed(html_text)
    return {'type': 'doc', 'version': 1, 'content': parser.result()}


_BLOCK_TAGS = frozenset(
    {
        'p',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'ul',
        'ol',
        'li',
        'blockquote',
        'pre',
        'table',
        'tr',
        'td',
        'th',
    }
)

_IGNORED_TAGS = frozenset({'thead', 'tbody', 'tfoot'})

_HEADING_MAP: dict[str, int] = {
    'h1': 1,
    'h2': 2,
    'h3': 3,
    'h4': 4,
    'h5': 5,
    'h6': 6,
}

_MARK_TAGS: dict[str, str] = {
    'strong': 'strong',
    'b': 'strong',
    'em': 'em',
    'i': 'em',
    'code': 'code',
    'del': 'strike',
    's': 'strike',
}


class _HTMLToADFParser(html.parser.HTMLParser):
    """Parse HTML produced by the markdown library into ADF nodes."""

    def __init__(self) -> None:
        super().__init__()
        self._doc: list[dict[str, typing.Any]] = []
        self._stack: list[dict[str, typing.Any]] = []
        self._marks: list[dict[str, typing.Any]] = []
        self._in_pre = False
        self._pre_text = ''
        self._code_lang: str | None = None
        self._href: str | None = None

    def result(self) -> list[dict[str, typing.Any]]:
        """Return the collected top-level ADF content nodes."""
        return self._doc

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attr_dict = dict(attrs)
        if tag == 'pre':
            self._in_pre = True
            self._pre_text = ''
            self._code_lang = None
            return
        if tag == 'code' and self._in_pre:
            cls = attr_dict.get('class', '') or ''
            match = re.match(r'language-(\S+)', cls)
            if match:
                self._code_lang = match.group(1)
            return
        if tag == 'a':
            href = attr_dict.get('href', '') or ''
            self._href = href
            self._marks.append({'type': 'link', 'attrs': {'href': href}})
            return
        if tag in _MARK_TAGS:
            self._marks.append({'type': _MARK_TAGS[tag]})
            return
        if tag == 'hr':
            self._doc.append({'type': 'rule'})
            return
        if tag == 'br':
            self._add_hard_break()
            return
        if tag in _IGNORED_TAGS:
            return
        if tag in _BLOCK_TAGS:
            node = self._make_block_node(tag)
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag == 'pre':
            self._in_pre = False
            node: dict[str, typing.Any] = {'type': 'codeBlock', 'content': []}
            if self._code_lang:
                node['attrs'] = {'language': self._code_lang}
            text = self._pre_text
            if text:
                node['content'].append({'type': 'text', 'text': text})
            self._doc.append(node)
            return
        if tag == 'code' and self._in_pre:
            return
        if tag == 'a':
            self._marks = [m for m in self._marks if m.get('type') != 'link']
            self._href = None
            return
        if tag in _MARK_TAGS:
            self._pop_mark(_MARK_TAGS[tag])
            return
        if tag in _IGNORED_TAGS:
            return
        if tag in _BLOCK_TAGS and self._stack:
            node = self._stack.pop()
            self._finish_block(node)

    def handle_data(self, data: str) -> None:
        if self._in_pre:
            self._pre_text += data
            return
        if not data.strip() and (
            not self._stack
            or self._stack[-1]['type']
            in ('bulletList', 'orderedList', 'blockquote', 'table', 'tableRow')
        ):
            return
        if not self._stack:
            if data.strip():
                self._doc.append(
                    {'type': 'paragraph', 'content': [self._text_node(data)]}
                )
            return
        current = self._stack[-1]
        content = current.setdefault('content', [])
        if current['type'] in ('listItem', 'tableCell', 'tableHeader'):
            if content and content[-1].get('type') == 'paragraph':
                content[-1]['content'].append(self._text_node(data))
            else:
                content.append(
                    {'type': 'paragraph', 'content': [self._text_node(data)]}
                )
        else:
            content.append(self._text_node(data))

    def _text_node(self, text: str) -> dict[str, typing.Any]:
        node: dict[str, typing.Any] = {'type': 'text', 'text': text}
        if self._marks:
            node['marks'] = list(self._marks)
        return node

    def _pop_mark(self, mark_type: str) -> None:
        """Remove the last mark of the given type from the mark stack."""
        for i in range(len(self._marks) - 1, -1, -1):
            if self._marks[i].get('type') == mark_type:
                self._marks.pop(i)
                break

    def _add_hard_break(self) -> None:
        node: dict[str, typing.Any] = {'type': 'hardBreak'}
        if self._stack:
            current = self._stack[-1]
            content = current.setdefault('content', [])
            content.append(node)
        else:
            self._doc.append(node)

    @staticmethod
    def _make_block_node(tag: str) -> dict[str, typing.Any]:
        if tag in _HEADING_MAP:
            return {
                'type': 'heading',
                'attrs': {'level': _HEADING_MAP[tag]},
                'content': [],
            }
        if tag == 'ul':
            return {'type': 'bulletList', 'content': []}
        if tag == 'ol':
            return {'type': 'orderedList', 'content': []}
        if tag == 'li':
            return {'type': 'listItem', 'content': []}
        if tag == 'blockquote':
            return {'type': 'blockquote', 'content': []}
        if tag == 'table':
            return {'type': 'table', 'content': []}
        if tag == 'tr':
            return {'type': 'tableRow', 'content': []}
        if tag == 'td':
            return {'type': 'tableCell', 'content': []}
        if tag == 'th':
            return {'type': 'tableHeader', 'content': []}
        return {'type': 'paragraph', 'content': []}

    def _finish_block(self, node: dict[str, typing.Any]) -> None:
        if self._stack:
            parent = self._stack[-1]
            parent_content = parent.setdefault('content', [])
            parent_content.append(node)
        else:
            self._doc.append(node)
