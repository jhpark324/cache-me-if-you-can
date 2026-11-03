"""Read-only checks of files that would enter version control. Never prints secrets."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote


@dataclass
class Finding:
    path: str
    rule: str
    line: int | None = None
    source: str = 'working-tree'


# Narrow recognizable secret formats; this is not a complete entropy scanner.
SECRET_PATTERNS = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'provider-key': re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}'),
    'github-token': re.compile(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}'),
    'jwt': re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}'),
    'literal-credential': re.compile(r'''["'](?:access_token|refresh_token|id_token|mcp_token|client_secret)["']\s*:\s*["'][A-Za-z0-9_./+=-]{32,}["']'''),
}
LINK = re.compile(r'!?\[[^\]]*\]\(([^)]+)\)')


def candidate_files(root: Path) -> tuple[list[str], bool]:
    """Include tracked files even when now ignored, plus non-ignored new files.

    A temporary bare Git directory applies the project's ignore rules before the
    first git init. Nothing is initialized or staged in the user's workspace.
    """
    root = root.resolve()
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                            capture_output=True, text=True)
    initialized = result.returncode == 0 and Path(result.stdout.strip()).resolve() == root
    with tempfile.TemporaryDirectory(prefix='cache-me-preflight-') as directory:
        if initialized:
            command = ['git', '-C', str(root)]
        else:
            subprocess.run(['git', 'init', '--bare', '-q', directory], check=True, capture_output=True)
            command = ['git', f'--git-dir={directory}', f'--work-tree={root}']
        output = subprocess.check_output(command + ['ls-files', '--cached', '--others', '--exclude-standard', '-z'])
    return sorted(set(n for n in output.decode('utf-8').split('\0') if n)), initialized


def unsafe_path(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1].lower()
    return (any(p in {'.venv', 'node_modules', '__pycache__', '.pytest_cache', '.cache', '.local'} for p in parts)
            or name in {'credentials.json', 'local-access.json', '.env'}
            or (name.startswith('.env.') and name != '.env.example')
            or re.search(r'\.(?:sqlite\d*|db)(?:[.-].*)?$', name) is not None
            or name.endswith(('.pem', '.key', '-backup.zip'))
            or any(p.endswith('.lance') for p in parts))


def text_findings(relative: str, content: str, *, source='working-tree') -> list[Finding]:
    findings = []
    for number, line in enumerate(content.splitlines(), 1):
        for rule, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append(Finding(relative, rule, number, source))
    return findings


def inspect_index(root: Path) -> dict:
    """Inspect the staged blobs, even if the working copy is clean or deleted.

    Only read Git objects referenced by the current index. Do not stage anything,
    rewrite the index, or walk commit history. Blob bytes never reach tool output.
    """
    root = root.resolve()
    command = ['git', '-C', str(root)]
    entries = subprocess.check_output(command + ['ls-files', '--stage', '-z']).split(b'\0')
    findings = []
    files = total_bytes = 0
    with subprocess.Popen(command + ['cat-file', '--batch'], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        for entry in filter(None, entries):
            metadata, name = entry.split(b'\t', 1)
            mode, object_id, stage = metadata.split()
            relative = name.decode('utf-8')
            files += 1
            if unsafe_path(relative):
                findings.append(Finding(relative, 'runtime-or-sensitive-file', source='index'))
            if stage != b'0':
                findings.append(Finding(relative, 'unmerged-index-entry', source='index'))
                continue
            if mode == b'120000':
                findings.append(Finding(relative, 'symlink-requires-review', source='index'))
                continue
            if mode == b'160000':
                findings.append(Finding(relative, 'submodule-requires-review', source='index'))
                continue
            process.stdin.write(object_id + b'\n')
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3 or header[1] != b'blob' or not header[2].isdigit():
                raise OSError('Could not read indexed Git blob')
            size = int(header[2])
            total_bytes += size
            # Drain large blobs without loading them into memory; size alone
            # blocks publication and is enough to require a separate review.
            remaining, chunks = size, []
            large = size > 10 * 1024 * 1024
            if large:
                findings.append(Finding(relative, 'large-file-over-10MiB', source='index'))
            while remaining:
                block = process.stdout.read(min(remaining, 1024 * 1024))
                if not block:
                    raise OSError('Incomplete indexed Git blob')
                remaining -= len(block)
                if not large:
                    chunks.append(block)
            if process.stdout.read(1) != b'\n':
                raise OSError('Invalid indexed Git blob terminator')
            if large:
                continue
            try:
                content = b''.join(chunks).decode('utf-8')
            except UnicodeDecodeError:
                continue
            findings.extend(text_findings(relative, content, source='index'))
        process.stdin.close()
        if process.wait() != 0:
            raise OSError('Git index scan did not complete')
    return {'files': files, 'bytes': total_bytes, 'findings': [asdict(f) for f in findings]}


def inspect(root: Path, candidates: list[str]) -> dict:
    root = root.resolve()
    findings: list[Finding] = []
    selected = set(candidates)
    total_bytes = 0
    markdown_count = 0
    for relative in candidates:
        path = root / relative
        if unsafe_path(relative):
            findings.append(Finding(relative, 'runtime-or-sensitive-file'))
        if path.is_symlink():
            # Do not follow a link outside the reviewed tree or publish local paths.
            findings.append(Finding(relative, 'symlink-requires-review'))
            continue
        if not path.is_file():
            continue  # A tracked deletion is not a publication candidate.
        size = path.stat().st_size
        total_bytes += size
        if size > 10 * 1024 * 1024:
            findings.append(Finding(relative, 'large-file-over-10MiB'))
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        findings.extend(text_findings(relative, content))
        if path.suffix != '.md':
            continue
        markdown_count += 1
        # Validate local Markdown links outside fenced examples; don't crawl URLs.
        clean = re.sub(r'```.*?```', '', content, flags=re.S)
        for match in LINK.finditer(clean):
            href = match[1].split(' "')[0].strip('<>')
            if re.match(r'\w+:|#|\{', href):
                continue
            target = (path.parent / unquote(href.split('#')[0])).resolve()
            try:
                name = target.relative_to(root).as_posix()
            except ValueError:
                findings.append(Finding(relative, 'link-outside-repository'))
                continue
            included = (name in selected if target.is_file() else
                        any(n.startswith(name.rstrip('/') + '/') for n in selected))
            if not target.exists() or not included:
                findings.append(Finding(relative, 'missing-or-excluded-link-target'))
    return {'files': len(candidates), 'bytes': total_bytes, 'markdown_files': markdown_count,
            'findings': [asdict(f) for f in findings]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        candidates, initialized = candidate_files(root)
        report = inspect(root, candidates)
        index = inspect_index(root) if initialized else {'files': 0, 'bytes': 0, 'findings': []}
        report['index_files'] = index['files']
        report['index_bytes'] = index['bytes']
        report['findings'].extend(index['findings'])
    except (OSError, subprocess.CalledProcessError):
        print('Preflight failed to enumerate/read files. Check Git installation and file permissions.')
        return 2
    report['git_initialized'] = initialized
    report['scope'] = ('working-tree candidates and current Git index blobs; local Markdown links checked against '
                       'working-tree candidates; excludes Git history, remote state, image contents and unknown secret formats')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['findings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
