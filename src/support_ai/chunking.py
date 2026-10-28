"""Line-preserving Markdown chunks; fenced commands remain intact."""

import hashlib
import re

from pydantic import BaseModel

from support_ai.git_reader import Document

CHUNKER_VERSION = "markdown-lines-v1"
TARGET_CHARS = 1400


class Chunk(BaseModel):
    id: str
    path: str
    commit: str
    ordinal: int
    start_line: int
    end_line: int
    content: str


def chunk_document(document: Document) -> list[Chunk]:
    """Split at headings/paragraphs, with a soft limit for indivisible blocks."""
    lines = document.content.splitlines(keepends=True)
    blocks: list[tuple[int, int]] = []
    start = 0
    fence_char = ""
    fence_length = 0
    for index, line in enumerate(lines):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence_char:
            if (fence and fence[1][0] == fence_char and len(fence[1]) >= fence_length
                    and not fence[2].strip()):
                fence_char = ""
            continue
        if re.match(r"^ {0,3}#{1,6}\s", line) and index > start:
            blocks.append((start, index))
            start = index
        if fence:
            fence_char, fence_length = fence[1][0], len(fence[1])
        elif not line.strip():
            blocks.append((start, index + 1))
            start = index + 1
    if start < len(lines):
        blocks.append((start, len(lines)))

    ranges: list[tuple[int, int]] = []
    for begin, end in blocks:
        text = "".join(lines[begin:end])
        heading = bool(re.match(r"^ {0,3}#{1,6}\s", lines[begin]))
        if ranges and not heading:
            old_begin, old_end = ranges[-1]
            if len("".join(lines[old_begin:old_end])) + len(text) <= TARGET_CHARS:
                ranges[-1] = (old_begin, end)
                continue
        ranges.append((begin, end))

    chunks = []
    for begin, end in ranges:
        content = "".join(lines[begin:end])
        if not content.strip():
            continue
        ordinal = len(chunks)
        identity = f"{CHUNKER_VERSION}\0{document.path}\0{document.sha256}\0{ordinal}"
        chunks.append(Chunk(
            id=hashlib.sha256(identity.encode()).hexdigest(), path=document.path,
            commit=document.commit, ordinal=ordinal, start_line=begin + 1,
            end_line=end, content=content,
        ))
    return chunks
