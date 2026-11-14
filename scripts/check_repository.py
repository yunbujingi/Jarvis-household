"""Inspect the Git index for private artifacts and broken documentation links.

This is a small project-specific guard, not a substitute for a secret scanner
or a human review of images, logs, dependency licenses and Git history.
"""
from pathlib import PurePosixPath
import re
import subprocess
import sys

ROOT_FILES = {'README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CHANGELOG.md', 'LICENSE',
              '.gitignore', '.dockerignore', 'pyproject.toml', 'requirements.lock'}
PREFIXES = ('src/jarvis_home/', 'tests/', 'scripts/', '.github/',
            'docs/guides/', 'docs/images/', 'deploy/community/')
PRIVATE_SUFFIXES = {'.sqlite3', '.db', '.pem', '.key', '.whl', '.zip', '.tar', '.gz'}
TEXT_SUFFIXES = {'.py', '.md', '.txt', '.toml', '.yaml', '.yml', '.json', '.js', '.css', '.html', '.svg', '.lock'}
PATTERNS = {
    'private home path': re.compile(r'/(?:Users|home)/[^/\s]+/(?:Developer|Downloads|\.ssh|\.codex)/'),
    'private NAS URL': re.compile(r'https?://[^\s/]+\.ug\.link'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'provider credential': re.compile(r'\b(?:sk-[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})'),
}


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    try:
        entries = git('ls-files', '--stage', '-z').decode().split('\0')
    except subprocess.CalledProcessError:
        raise SystemExit('Run from an initialized repository after staging files.')
    files = {}
    errors = []
    for entry in filter(None, entries):
        meta, name = entry.split('\t', 1)
        mode, sha, stage = meta.split()
        if stage != '0' or mode == '120000':
            errors.append(f'{name}: unresolved stage or symlink')
        if name not in ROOT_FILES and not name.startswith(PREFIXES):
            errors.append(f'{name}: outside reviewed publishable paths')
        path = PurePosixPath(name)
        if path.suffix.lower() in PRIVATE_SUFFIXES or any(p.startswith('.env') for p in path.parts):
            errors.append(f'{name}: private/generated artifact')
        data = git('cat-file', 'blob', sha)
        files[name] = data
        if len(data) > 2_000_000:
            errors.append(f'{name}: large file requires review')
        if path.suffix in TEXT_SUFFIXES or name in ROOT_FILES or path.name == 'Dockerfile':
            try:
                content = data.decode()
            except UnicodeDecodeError:
                errors.append(f'{name}: expected UTF-8')
                continue
            for label, pattern in PATTERNS.items():
                if pattern.search(content):
                    errors.append(f'{name}: possible {label}')
            # Short known protocol-test values are intentional fixtures.
            for value in re.findall(r'[?&]token=([^&\s\"\'<>]+)', content):
                if value not in {'x', 'y', 'test-only', '%0A', 'x#fragment'}:
                    errors.append(f'{name}: possible endpoint credential')
    if not files:
        errors.append('No staged/tracked files to review.')
    for name, data in files.items():
        if not name.endswith('.md'):
            continue
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', data.decode()):
            target = target.split('#', 1)[0].strip('<>')
            if not target or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                continue
            parts = []
            for part in (PurePosixPath(name).parent / target).parts:
                if part == '..':
                    if parts:
                        parts.pop()
                elif part != '.':
                    parts.append(part)
            resolved = '/'.join(parts)
            if resolved not in files:
                errors.append(f'{name}: link missing from Git index: {target}')
    if errors:
        print('\n'.join(errors))
        return 1
    print(f'Repository check passed: {len(files)} files; no blocked artifacts or broken local Markdown links.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
