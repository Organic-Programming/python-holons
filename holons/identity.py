from __future__ import annotations

"""Parse HOLON.md identity files.

A HOLON.md file contains YAML frontmatter between --- delimiters,
followed by markdown content.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class HolonIdentity:
    """Parsed identity from a HOLON.md file."""

    uuid: str = ""
    given_name: str = ""
    family_name: str = ""
    motto: str = ""
    composer: str = ""
    clade: str = ""
    status: str = ""
    born: str = ""
    lang: str = ""
    parents: list[str] = field(default_factory=list)
    reproduction: str = ""
    generated_by: str = ""
    proto_status: str = ""
    aliases: list[str] = field(default_factory=list)


def parse_holon(path: str | Path) -> HolonIdentity:
    """Parse a HOLON.md file and return its identity.

    Raises FileNotFoundError if the file doesn't exist.
    Raises ValueError if the frontmatter is invalid.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    # Extract YAML frontmatter
    if not text.startswith("---"):
        raise ValueError(f"{path}: missing YAML frontmatter")

    end = text.index("---", 3)
    frontmatter = text[3:end].strip()

    data = yaml.safe_load(frontmatter)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: frontmatter is not a YAML mapping")

    return HolonIdentity(
        uuid=data.get("uuid", ""),
        given_name=data.get("given_name", ""),
        family_name=data.get("family_name", ""),
        motto=data.get("motto", ""),
        composer=data.get("composer", ""),
        clade=data.get("clade", ""),
        status=data.get("status", ""),
        born=data.get("born", ""),
        lang=data.get("lang", ""),
        parents=data.get("parents", []),
        reproduction=data.get("reproduction", ""),
        generated_by=data.get("generated_by", ""),
        proto_status=data.get("proto_status", ""),
        aliases=data.get("aliases", []),
    )
