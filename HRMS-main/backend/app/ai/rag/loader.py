import re
from pathlib import Path

from pypdf import PdfReader

from app.core.config import settings
from app.models.hr_policy import HRPolicy


def load_policy_sections(policy: HRPolicy) -> list[tuple[str, str]]:
    """Return policy text grouped by Markdown heading or PDF page."""
    if policy.content and policy.content.strip():
        return _markdown_sections(policy.content, policy.title)

    if not policy.file_path:
        return []

    policy_path = Path(policy.file_path).resolve()
    policy_dir = Path(settings.policy_upload_dir).resolve()
    if policy_dir not in policy_path.parents or not policy_path.is_file():
        return []

    suffix = policy_path.suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(str(policy_path))
            return [
                (f"Page {page_number}", page.extract_text() or "")
                for page_number, page in enumerate(reader.pages, start=1)
            ]
        except Exception:
            return []

    if suffix in {".txt", ".md"}:
        try:
            return _markdown_sections(policy_path.read_text(encoding="utf-8"), policy.title)
        except (OSError, UnicodeError):
            return []

    return []


def _markdown_sections(text: str, fallback_section: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = fallback_section
    current_lines: list[str] = []

    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = heading.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))

    return [
        (heading, "\n".join(lines).strip())
        for heading, lines in sections
        if "\n".join(lines).strip()
    ]
