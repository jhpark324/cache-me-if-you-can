"""Render selected Mermaid docs with an optional external CLI, then build a gallery."""
from __future__ import annotations

import argparse
import html
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    ('architecture/current-system.md', '구현', ['시스템과 신뢰 경계', '실행 모듈', '정본 데이터 관계', '배포와 실행 데이터']),
    ('architecture/runtime-flows.md', '구현', ['저장과 비동기 처리', '단일 질문과 답변', '수정과 출처 자격', '삭제 확인과 동시성', '로그인과 취소']),
    ('architecture/maintenance-review.md', '개선 방향', ['리팩토링 순서']),
    ('project/evolution-proposals.md', '제품 제안', ['차별화 기능의 연결']),
    ('research/second-brain-comparison-2026-11.md', '구현·조사', ['로컬 저장과 외부 추론']),
    ('architecture/component-boundaries.md', '구현', ['공통 필터 의미', '웹 컴포넌트 경계']),
]
CSS = '''@font-face{font-family:SUIT;src:url('../../frontend/public/fonts/SUIT-Variable.woff2')}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#09090b;color:#f4f4f5;font-family:SUIT,sans-serif;line-height:1.6}a{color:#ffac72;text-underline-offset:4px}a:focus-visible{outline:3px solid #ffac72;outline-offset:5px}header{max-width:1320px;margin:auto;padding:56px 28px 24px}h1{font-size:clamp(28px,4vw,48px);margin:0;letter-spacing:-.035em}header p{max-width:780px;color:#c8c8cd}nav{display:flex;flex-wrap:wrap;gap:10px 18px;margin-top:24px}nav a{padding:6px 0}main{max-width:1320px;margin:auto;padding:0 28px 64px}section{scroll-margin-top:20px;border-top:1px solid #33333a;padding:30px 0;margin-top:22px}.caption{display:flex;align-items:center;justify-content:space-between;gap:16px}h2{font-size:22px;margin:0}.caption span{font-size:13px;color:#ffac72;white-space:nowrap}section p{margin:8px 0 18px;font-size:14px}.diagram{display:block;background:white;border-radius:12px;padding:20px;overflow:auto}.diagram img{display:block;width:100%;height:auto;min-width:580px}@media(max-width:600px){header{padding-top:30px}main,header{padding-left:16px;padding-right:16px}.caption{align-items:flex-start}h2{font-size:20px}.diagram{padding:12px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{body{background:white;color:black}nav{display:none}section{break-inside:avoid}a{color:#333}.diagram img{min-width:0}}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mermaid-cli', help='mmdc executable; omit to use existing SVGs')
    parser.add_argument('--puppeteer-config', type=Path)
    parser.add_argument('--mermaid-config', type=Path)
    args = parser.parse_args()
    directory = ROOT / 'docs/architecture/diagrams'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cache-me-diagrams-') as temporary:
        for source, _, titles in DOCUMENTS:
            document = ROOT / 'docs' / source
            if document.read_text(encoding='utf-8').count('```mermaid') != len(titles):
                raise SystemExit(f'Diagram list differs from {source}; update DOCUMENTS.')
            if not args.mermaid_cli:
                continue
            command = [args.mermaid_cli, '-i', str(document), '-o', str(Path(temporary) / (document.stem + '-rendered.md')),
                       '-a', str(directory), '--no-font-embed', '-j', '1']
            for option, value in [('-p', args.puppeteer_config), ('-c', args.mermaid_config)]:
                if value:
                    command += [option, str(value.resolve())]
            subprocess.run(command, check=True)
    links, figures, rows = [], [], []
    for source, status, titles in DOCUMENTS:
        for index, title in enumerate(titles, 1):
            name = f'{Path(source).stem}-rendered-{index}.svg'
            if not (directory / name).is_file():
                raise SystemExit(f'Missing {name}; supply --mermaid-cli to render first.')
            key = f'diagram-{len(figures) + 1}'
            links.append(f'<a href="#{key}">{html.escape(title)}</a>')
            figures.append(f'<section id="{key}"><div class="caption"><h2>{html.escape(title)}</h2><span>{html.escape(status)}</span></div>'
                           f'<p><a href="../{source}">설명과 근거 문서</a></p><a class="diagram" href="diagrams/{name}">'
                           f'<img src="diagrams/{name}" alt="{html.escape(title)} 다이어그램" loading="lazy"></a></section>')
            rows.append(f'| [{title}]({name}) | {status} | [원문](../../{source}) |')
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += f'<title>Cache Me If You Can — 구조와 흐름</title><style>{CSS}</style><header><h1>Cache Me If You Can</h1><p>현재 구조와 실행 흐름</p>'
    page += '<p>구현된 동작과 앞으로의 제안을 구분했습니다. 도식을 클릭하면 SVG 원본을 열 수 있습니다. 작은 화면에서는 도식 안을 가로로 스크롤할 수 있습니다.</p>'
    page += '<nav aria-label="다이어그램 목록">' + ''.join(links) + '</nav></header><main>' + ''.join(figures) + '</main></html>'
    (directory.parent / 'overview.html').write_text(page, encoding='utf-8')
    intro = '# 아키텍처 다이어그램\n\n[전체 보기](../overview.html)에서 도식과 원문을 함께 탐색한다. 각 문서의 Mermaid가 수정 원본이며 아래 SVG는 렌더링 결과다. 현재 구현과 제안을 구분한다.\n\n| 도식 | 상태 | 수정 원본 |\n| --- | --- | --- |\n'
    footer = '''
## 다시 생성

Mermaid CLI를 별도 도구 환경에 준비한 뒤 프로젝트 루트에서 실행한다. 제품 의존성에는 포함하지 않는다. CLI 12 계열과 Chromium을 기준으로 하며 브라우저·한글 글꼴과 OS 실행 의존성이 필요하다.

```sh
python scripts/render_diagrams.py --mermaid-cli <mmdc 실행 경로>
```

필요하면 `--puppeteer-config`로 Chromium 경로와 실행 인자를, `--mermaid-config`로 테마·글꼴을 지정한다. SVG가 이미 있으면 인자 없이 HTML과 인덱스만 다시 생성한다. 문서에 도식을 추가하면 스크립트의 목록·제목도 갱신한다.
'''
    (directory / 'index.md').write_text(intro + '\n'.join(rows) + '\n' + footer, encoding='utf-8')
    print(f'Created diagram gallery and index: {len(figures)} diagrams.')


if __name__ == '__main__':
    main()
