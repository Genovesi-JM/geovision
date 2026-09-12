"""Build an allowlisted, credential-free context outside the repository.

This does not build/push an image, log in, or deploy. Only git-indexed root HTML
and assets are considered; gateway.py and this Dockerfile are explicit inputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess


SOURCE_DIR = Path(__file__).resolve().parent
DEFAULT_REPO = SOURCE_DIR.parents[2]
GATEWAY_REPOSITORY = 'geovisionpilothcwka3w.azurecr.io/geovision-online-gateway'
SUFFIXES = {'.html', '.js', '.css', '.json', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.woff', '.woff2', '.ttf'}
NOOP_FILES = {'assets/js/contacts.js', 'assets/js/chatbot.js'}
CONFIG_SCRIPT = b'<script src="/_gateway/config.js"></script>'
NOOP_CONTENT = b'/* Optional contacts/chatbot integrations are disabled in this protected pilot. */\n'
SENSITIVE_PART = re.compile(r'(^|[._\-])(secrets?|credentials?|passwords?|tokens?|private|backups?|database|dumps?|dotenv)([._\-]|$)', re.I)
PRIVATE_MATERIAL = re.compile(br'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|PRIVATE_BUILD_SECRET_CANARY|PRIVATE_SYNTHETIC_PASSWORD_MARKER')
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_CONTEXT_BYTES = 512 * 1024 * 1024


class UnsafeBuildInput(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise UnsafeBuildInput(reason)


def validate_gateway_image(image):
    """Reusable deployment preflight; never accept a tag or another registry."""
    require(isinstance(image, str) and re.fullmatch(re.escape(GATEWAY_REPOSITORY) + r'@sha256:[a-f0-9]{64}', image) is not None, 'invalid_gateway_image')
    return image.rsplit('@', 1)[1]


def tracked_paths(repo):
    result = subprocess.run(['git', 'ls-files', '-z', '--', '*.html', 'assets/**'], cwd=repo, capture_output=True, check=True, timeout=30)
    return [part.decode('utf-8') for part in result.stdout.split(b'\0') if part]


def checked_relative(raw):
    require(isinstance(raw, str) and raw and not any(char in raw for char in ('\\', '?', '#', '%')) and not any(ord(char) < 32 or ord(char) == 127 for char in raw), 'unsafe_static_path')
    path = PurePosixPath(raw)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in raw.split('/')), 'unsafe_static_path')
    # Includes files such as assets/.env and assets/private/credentials.json,
    # even when their suffix would otherwise be ignored.
    in_scope = (len(path.parts) == 1 and path.suffix.lower() == '.html') or path.parts[0] == 'assets'
    # This existing public password-reset UI is source code, not a password
    # export. No similarly named JSON, asset or nested path is exempted.
    if in_scope and raw != 'reset-password.html':
        require(not any(part.startswith('.') or SENSITIVE_PART.search(part) for part in path.parts), 'sensitive_static_path')
    return path


def read_regular(repo, relative):
    path = repo.joinpath(*relative.parts)
    cursor = repo
    for part in relative.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), 'symlink_source')
    try:
        path.resolve(strict=True).relative_to(repo)
    except (ValueError, FileNotFoundError):
        raise UnsafeBuildInput('source_escapes_or_missing') from None
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_FILE_BYTES, 'invalid_source_file')
        content = stream.read(MAX_FILE_BYTES + 1)
    require(len(content) <= MAX_FILE_BYTES, 'source_too_large')
    require(PRIVATE_MATERIAL.search(content) is None, 'private_material_in_source')
    return content


def transform_static(relative, content):
    if relative in NOOP_FILES:
        return NOOP_CONTENT
    if relative.endswith('.html'):
        head = re.search(br'<head\b[^>]*>', content, re.I)
        require(head is not None, 'html_head_missing')
        early_script = re.search(br'<script\b', content, re.I)
        require(early_script is None or early_script.start() >= head.end(), 'html_script_before_head')
        require(CONFIG_SCRIPT not in content, 'config_already_in_source')
        content = content[:head.end()] + b'\n' + CONFIG_SCRIPT + b'\n' + content[head.end():]
    return content


def prepare_context(repo, output):
    repo = Path(repo).resolve(strict=True)
    output = Path(output).absolute()
    require(not output.is_symlink(), 'symlink_output')
    resolved_output = output.resolve()
    require(resolved_output != repo and repo not in resolved_output.parents, 'output_must_be_outside_repo')
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), 'output_must_be_empty')
    require(output.parent.exists(), 'output_parent_missing')
    files = {}
    total = 0
    for raw in sorted(set(tracked_paths(repo))):
        relative = checked_relative(raw)
        root_html = len(relative.parts) == 1 and relative.suffix.lower() == '.html'
        asset = len(relative.parts) > 1 and relative.parts[0] == 'assets'
        if not (root_html or asset) or relative.suffix.lower() not in SUFFIXES:
            continue
        content = transform_static(raw, read_regular(repo, relative))
        total += len(content)
        require(total <= MAX_CONTEXT_BYTES, 'context_too_large')
        files[raw] = content
    require({'login.html', 'admin.html'} <= set(files), 'required_static_pages_missing')
    gateway = read_regular(repo, PurePosixPath('infra/azure/online_gateway/gateway.py'))
    dockerfile = read_regular(repo, PurePosixPath('infra/azure/online_gateway/Dockerfile'))
    manifest = {'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    # Write only after every source has passed validation; never modify source.
    output.mkdir(mode=0o700, exist_ok=True)
    for name, content in files.items():
        destination = output / 'public' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (output / 'gateway.py').write_bytes(gateway)
    (output / 'Dockerfile').write_bytes(dockerfile)
    (output / 'manifest.json').write_bytes(manifest_bytes)
    (output / '.dockerignore').write_text('*\n!Dockerfile\n!gateway.py\n!manifest.json\n!public/\n!public/**\n', encoding='utf-8')
    return {'result': 'SOURCE_ONLY_GATEWAY_CONTEXT_READY', 'files': len(files), 'static_bytes': total,
            'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'gateway_sha256': hashlib.sha256(gateway).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--output', type=Path, required=True, help='Existing empty or new directory outside the source repository.')
    args = parser.parse_args()
    try:
        result = prepare_context(args.repo, args.output)
    except (UnsafeBuildInput, OSError, subprocess.SubprocessError, UnicodeError):
        print(json.dumps({'result': 'GATEWAY_CONTEXT_REJECTED', 'details': 'No source or credential contents emitted.'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
