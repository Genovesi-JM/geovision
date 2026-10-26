"""Prepare a public static-site artifact without backend files or credentials.

Only tracked root HTML and tracked public assets are eligible. Reuse the pilot
packager's path, symlink, size and private-material checks, but do not apply its
restricted gateway configuration or disable public website features.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
DEFAULT_REPO = SOURCE_DIR.parents[2]
API_ORIGIN = "https://api.geovisionops.com"
SUFFIXES = {
    ".html", ".js", ".mjs", ".css", ".json", ".svg", ".png", ".jpg",
    ".jpeg", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".mp4", ".webm",
    ".avif", ".gif", ".webmanifest",
}
spec = importlib.util.spec_from_file_location(
    "geovision_static_input_guard", SOURCE_DIR.parent / "online_gateway/build_context.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def prepare_site(repo, output):
    repo = Path(repo).resolve(strict=True)
    output = Path(output).absolute()
    guard.require(not output.is_symlink(), "symlink_output")
    resolved = output.resolve()
    guard.require(resolved != repo and repo not in resolved.parents, "output_must_be_outside_repo")
    guard.require(output.parent.exists(), "output_parent_missing")
    guard.require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output_must_be_empty")
    files = {}
    total = 0
    for raw in sorted(set(guard.tracked_paths(repo))):
        relative = guard.checked_relative(raw)
        if not ((len(relative.parts) == 1 and relative.suffix == ".html")
                or (len(relative.parts) > 1 and relative.parts[0] == "assets")):
            continue
        if relative.suffix.lower() not in SUFFIXES:
            continue
        content = guard.read_regular(repo, relative)
        if raw == "assets/js/config.js":
            # Azure preview hosts must not accidentally use localhost. Retain
            # the stable canonical API host through the eventual DNS cutover.
            content = ("window.API_BASE = " + json.dumps(API_ORIGIN) + ";\n").encode() + content
        total += len(content)
        guard.require(total <= 240 * 1024 * 1024, "static_site_too_large")
        files[raw] = content
    guard.require({"index.html", "login.html", "assets/js/config.js"} <= set(files), "required_site_files_missing")
    config = {
        "globalHeaders": {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
        },
        "routes": [
            {"route": "/", "headers": {"Cache-Control": "no-cache"}},
            {"route": "/*.html", "headers": {"Cache-Control": "no-cache"}},
            {"route": "/assets/js/*", "headers": {"Cache-Control": "no-cache"}},
            {"route": "/assets/css/*", "headers": {"Cache-Control": "no-cache"}},
        ],
        "mimeTypes": {".mjs": "text/javascript", ".webmanifest": "application/manifest+json"},
    }
    files["staticwebapp.config.json"] = (json.dumps(config, indent=2) + "\n").encode()
    # Complete input validation before creating any deployable artifact.
    output.mkdir(mode=0o700, exist_ok=True)
    for name, content in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return {
        "status": "static_artifact_ready",
        "api_origin": API_ORIGIN,
        "file_count": len(files),
        "bytes": sum(len(value) for value in files.values()),
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Local evidence outside the deployment artifact")
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    output = args.output.resolve()
    guard.require(manifest != output and output not in manifest.parents, "manifest_must_be_outside_artifact")
    result = prepare_site(args.repo, args.output)
    manifest.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "files"}))
