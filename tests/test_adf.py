"""Tests for the markdown -> ADF converter."""

from imbi_automations import adf
from tests import base


class TestMarkdownToADF(base.AsyncTestCase):
    async def test_blank_input_produces_single_empty_paragraph(self) -> None:
        self.assertEqual(
            adf.markdown_to_adf(''),
            {
                'type': 'doc',
                'version': 1,
                'content': [{'type': 'paragraph', 'content': []}],
            },
        )

    async def test_heading(self) -> None:
        doc = adf.markdown_to_adf('# Title')
        self.assertEqual(doc['content'][0]['type'], 'heading')
        self.assertEqual(doc['content'][0]['attrs'], {'level': 1})
        self.assertEqual(
            doc['content'][0]['content'], [{'type': 'text', 'text': 'Title'}]
        )

    async def test_inline_marks(self) -> None:
        doc = adf.markdown_to_adf('A **b** _i_ `c` text.')
        para = doc['content'][0]
        self.assertEqual(para['type'], 'paragraph')
        marks = [
            (node.get('text'), [m['type'] for m in node.get('marks', [])])
            for node in para['content']
        ]
        self.assertIn(('b', ['strong']), marks)
        self.assertIn(('i', ['em']), marks)
        self.assertIn(('c', ['code']), marks)

    async def test_link(self) -> None:
        doc = adf.markdown_to_adf('[hi](https://example.com)')
        para = doc['content'][0]
        text = para['content'][0]
        self.assertEqual(text['text'], 'hi')
        self.assertEqual(
            text['marks'],
            [{'type': 'link', 'attrs': {'href': 'https://example.com'}}],
        )

    async def test_bullet_list(self) -> None:
        doc = adf.markdown_to_adf('- one\n- two')
        lst = doc['content'][0]
        self.assertEqual(lst['type'], 'bulletList')
        self.assertEqual(len(lst['content']), 2)
        for item in lst['content']:
            self.assertEqual(item['type'], 'listItem')
            self.assertEqual(item['content'][0]['type'], 'paragraph')

    async def test_fenced_code_block(self) -> None:
        doc = adf.markdown_to_adf('```python\nprint(1)\n```')
        block = doc['content'][0]
        self.assertEqual(block['type'], 'codeBlock')
        self.assertEqual(block['attrs'], {'language': 'python'})
        self.assertEqual(block['content'][0]['text'], 'print(1)\n')

    async def test_stray_br_at_root_is_dropped(self) -> None:
        parser = adf._HTMLToADFParser()
        parser.feed('<br>')
        self.assertEqual(parser.result(), [])

    async def test_hr_inside_blockquote_stays_nested(self) -> None:
        doc = adf.markdown_to_adf('> before\n>\n> ---\n>\n> after')
        self.assertEqual(len(doc['content']), 1)
        bq = doc['content'][0]
        self.assertEqual(bq['type'], 'blockquote')
        child_types = [c['type'] for c in bq['content']]
        self.assertIn('rule', child_types)

    async def test_fenced_code_inside_list_item_stays_nested(self) -> None:
        parser = adf._HTMLToADFParser()
        parser.feed(
            '<ul><li><p>item</p><pre><code>print(1)\n</code></pre></li></ul>'
        )
        result = parser.result()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['type'], 'bulletList')
        item = result[0]['content'][0]
        child_types = [c['type'] for c in item['content']]
        self.assertIn('codeBlock', child_types)

    async def test_table(self) -> None:
        md = '| A | B |\n|---|---|\n| 1 | 2 |'
        doc = adf.markdown_to_adf(md)
        table = doc['content'][0]
        self.assertEqual(table['type'], 'table')
        header_row, body_row = table['content']
        self.assertEqual(header_row['content'][0]['type'], 'tableHeader')
        self.assertEqual(
            header_row['content'][0]['content'][0]['content'][0]['text'], 'A'
        )
        self.assertEqual(body_row['content'][0]['type'], 'tableCell')
        self.assertEqual(
            body_row['content'][0]['content'][0]['content'][0]['text'], '1'
        )
