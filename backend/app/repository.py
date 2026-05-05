"""Read-only, bounded repository access. Never imports or executes target code."""
import os
import re
from pathlib import Path

SKIP_DIRS = {"node_modules", "venv", "env", "__pycache__", "dist", "build", "vendor", "site-packages"}
EXTENSIONS = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}
SECRET_NAME = re.compile(r"secret|credential|password|token|private.?key|^id_rsa|^id_ed25519", re.I)
SECRET_CONTENT = re.compile(r"-----BEGIN .*PRIVATE KEY|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})|(?:api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\"\n]{8,}['\"]", re.I)
MAX_BYTES = 100_000
MAX_FILES = 300
MAX_ENTRIES = 3000
MAX_LINES = 40
MAX_SNIPPET_CHARS = 5000


class Repository:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Repository root must be a directory")

    @staticmethod
    def _allowed_part(part: str) -> bool:
        return not (part.startswith(".") or part.lower() in SKIP_DIRS or SECRET_NAME.search(part))

    def _path(self, relative: str) -> Path:
        path = Path(relative)
        if not relative or path.is_absolute() or ":" in relative or ".." in path.parts:
            raise ValueError("Only repository-relative paths are allowed")
        current = self.root
        for part in path.parts:
            if not self._allowed_part(part):
                raise ValueError("Excluded path")
            current = current / part
            if current.is_symlink() or current.is_junction():
                raise ValueError("Links are excluded")
        resolved = current.resolve(strict=True)
        if not resolved.is_relative_to(self.root):
            raise ValueError("Path escapes repository")
        if not resolved.is_file() or resolved.suffix.lower() not in EXTENSIONS:
            raise ValueError("Unsupported file")
        return resolved

    def _text(self, relative: str) -> str:
        path = self._path(relative)
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or b"\x00" in raw:
            raise ValueError("Binary or oversized file")
        text = raw.decode("utf-8")
        if SECRET_CONTENT.search(text):
            raise ValueError("Potential secret content excluded")
        return text

    def list_files(self) -> list[str]:
        files, pending, visited = [], [self.root], 0
        while pending and visited < MAX_ENTRIES and len(files) < MAX_FILES:
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > MAX_ENTRIES or len(files) >= MAX_FILES:
                            break
                        path = Path(entry.path)
                        if not self._allowed_part(entry.name) or entry.is_symlink() or path.is_junction():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(path)
                        elif entry.is_file(follow_symlinks=False):
                            relative = path.relative_to(self.root).as_posix()
                            try:
                                self._text(relative)
                                files.append(relative)
                            except (OSError, ValueError):
                                continue
            except OSError:
                continue
        return sorted(files)

    def read_file(self, path: str, start_line: int = 1, end_line: int = 40) -> dict:
        if start_line < 1 or end_line < start_line:
            raise ValueError("Invalid line range")
        lines = self._text(path).splitlines()
        if start_line > len(lines):
            raise ValueError("Start line exceeds file")
        end = min(end_line, start_line + MAX_LINES - 1, len(lines))
        selected, size = [], 0
        for line in lines[start_line - 1:end]:
            if size + len(line) + 1 > MAX_SNIPPET_CHARS:
                break
            selected.append(line)
            size += len(line) + 1
        if not selected:
            raise ValueError("Line exceeds snippet budget")
        return {"path": Path(path).as_posix(), "start_line": start_line,
                "end_line": start_line + len(selected) - 1, "content": "\n".join(selected)}

    def search_code(self, terms: list[str], limit: int = 8) -> list[dict]:
        terms = [term.casefold()[:80] for term in terms[:8] if term.strip()]
        hits = []
        for path in self.list_files():
            try:
                lines = self._text(path).splitlines()
                for number, line in enumerate(lines, 1):
                    if any(term in line.casefold() or term in path.casefold() for term in terms):
                        hits.append(self.read_file(path, max(1, number - 5), number + 14))
                        if len(hits) >= min(max(limit, 1), 8):
                            return hits
                        # One useful context window per file per round.
                        break
            except (OSError, ValueError):
                continue
        return hits

