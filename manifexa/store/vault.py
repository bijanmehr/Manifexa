"""The vault — a directory of Markdown files that *is* the source of truth.

Each entity lives at ``<root>/<type>/<slug>.md``. The path encodes the id, so
the filesystem and the graph never disagree about identity.
"""
from __future__ import annotations

from pathlib import Path

from .entity import Entity


class Vault:
    def __init__(self, root) -> None:
        self.root = Path(root)

    def path_for(self, entity_id: str) -> Path:
        return self.root / f"{entity_id}.md"

    def id_for(self, path: Path) -> str:
        return path.relative_to(self.root).with_suffix("").as_posix()

    def exists(self, entity_id: str) -> bool:
        return self.path_for(entity_id).exists()

    def write(self, entity: Entity) -> None:
        path = self.path_for(entity.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entity.to_markdown(), encoding="utf-8")

    def read(self, entity_id: str) -> Entity:
        text = self.path_for(entity_id).read_text(encoding="utf-8")
        return Entity.from_markdown(entity_id, text)

    def delete(self, entity_id: str) -> None:
        self.path_for(entity_id).unlink(missing_ok=True)

    def list(self) -> list[Entity]:
        return [
            Entity.from_markdown(self.id_for(p), p.read_text(encoding="utf-8"))
            for p in sorted(self.root.rglob("*.md"))
        ]

    def list_ids(self) -> list[str]:
        return [self.id_for(p) for p in sorted(self.root.rglob("*.md"))]
