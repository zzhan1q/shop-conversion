"""Render the offline dashboard from the saved analysis results."""

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def items(values):
    return ''.join(f'<li>{escape(value)}</li>' for value in values)


def render(case, template):
    fields = {
        key.upper(): escape(case[key])
        for key in ('title', 'eyebrow', 'subtitle', 'question', 'action')
    }
    fields.update(
        (key.upper(), items(case[key]))
        for key in ('findings', 'limits', 'method', 'checks')
    )
    sources = []
    for source in case['sources']:
        url = urlsplit(source['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Expected a public HTTPS source URL')
        sources.append(
            f'<a href="{escape(source["url"])}" rel="noreferrer">{escape(source["name"])}</a>'
        )
    fields['SOURCES'] = ' · '.join(sources)
    fields['GROUPS'] = json.dumps(
        case['groups'], ensure_ascii=False, allow_nan=False, separators=(',', ':')
    ).replace('<', r'\u003c')
    return re.sub(r'__([A-Z]+)__', lambda match: fields[match[1]], template)


def main():
    case = json.loads((ROOT / 'case.json').read_text(encoding='utf-8-sig'))
    template = (ROOT / 'dashboard.template.html').read_text(encoding='utf-8')
    (ROOT / 'dashboard.html').write_text(render(case, template), encoding='utf-8')


if __name__ == '__main__':
    main()
