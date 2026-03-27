from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from config import PROJECTS_DIR


def is_github_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == "github.com"


def _parse_github_reference(url: str) -> tuple[str, str, str | None]:
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only github.com repository URLs are supported")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URL must point to a repository")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    ref: str | None = None
    if len(parts) >= 4 and parts[2] == "tree":
        ref = "/".join(parts[3:]) or None
    return owner, repo, ref


def _repo_cache_dir(owner: str, repo: str, ref: str | None) -> Path:
    suffix = ref.replace("/", "__") if ref else "default"
    return PROJECTS_DIR / "github-cache" / owner / f"{repo}__{suffix}"


def _archive_url(owner: str, repo: str, ref: str | None) -> str:
    return f"https://codeload.github.com/{owner}/{repo}/zip/{ref or 'HEAD'}"


def _git_checkout(source_url: str, target_dir: Path, ref: str | None) -> Path:
    git_binary = shutil.which("git")
    if not git_binary:
        raise RuntimeError("git is not available")

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if not target_dir.exists():
        command = [git_binary, "clone", "--depth", "1"]
        if ref:
            command.extend(["--branch", ref])
        command.extend([source_url, str(target_dir)])
        subprocess.run(command, check=True, capture_output=True, text=True)
        return target_dir

    if not (target_dir / ".git").exists():
        raise RuntimeError(f"Cached repository is missing git metadata: {target_dir}")

    subprocess.run([git_binary, "-C", str(target_dir), "fetch", "--depth", "1", "origin"], check=True, capture_output=True, text=True)
    if ref:
        subprocess.run([git_binary, "-C", str(target_dir), "checkout", ref], check=True, capture_output=True, text=True)
        subprocess.run([git_binary, "-C", str(target_dir), "pull", "--ff-only", "origin", ref], check=True, capture_output=True, text=True)
    else:
        subprocess.run([git_binary, "-C", str(target_dir), "pull", "--ff-only"], check=True, capture_output=True, text=True)
    return target_dir


def _download_archive(owner: str, repo: str, ref: str | None, target_dir: Path) -> Path:
    archive_dir = target_dir.parent
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{repo}.zip"

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        response = client.get(_archive_url(owner, repo, ref))
        response.raise_for_status()
        archive_path.write_bytes(response.content)

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(target_dir)

    extracted_roots = [path for path in target_dir.iterdir() if path.is_dir()]
    if len(extracted_roots) == 1:
        return extracted_roots[0]
    return target_dir


def resolve_source_path(path_or_url: str) -> tuple[Path, str, str | None]:
    raw_value = path_or_url.strip()
    if not raw_value:
        raise ValueError("A local path or GitHub repository URL is required")

    if not is_github_url(raw_value):
        local_path = Path(raw_value).expanduser().resolve()
        if not local_path.exists() or not local_path.is_dir():
            raise ValueError("Provided path is not a directory")
        return local_path, "local_path", None

    owner, repo, ref = _parse_github_reference(raw_value)
    clone_url = f"https://github.com/{owner}/{repo}.git"
    source_url = f"https://github.com/{owner}/{repo}"
    if ref:
        source_url = f"{source_url}/tree/{ref}"
    target_dir = _repo_cache_dir(owner, repo, ref)

    try:
        resolved = _git_checkout(clone_url, target_dir, ref)
    except Exception:
        resolved = _download_archive(owner, repo, ref, target_dir)

    return resolved.resolve(), "github_url", source_url