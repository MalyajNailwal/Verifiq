"""Versioned prompt-template loading.

Prompts live in `app/prompts/` as `name_vN.txt` files. Placeholders use
`{{variable}}` syntax (JSON braces inside few-shot examples stay untouched).
Every template must declare its version in the filename; agents log the
name+version with each LLM call.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class PromptNotFoundError(Exception):
    pass


def _render(template: str, variables: dict[str, Any]) -> str:
    out = template
    for key, value in variables.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


@lru_cache(maxsize=64)
def load_prompt(name: str, version: str = "v1") -> tuple[str, str]:
    """Return (template_text, prompt_version). Cached; files are read-only at runtime."""
    filename = f"{name}_{version}.txt"
    path = PROMPTS_DIR / filename
    if not path.is_file():
        raise PromptNotFoundError(f"prompt template not found: {filename}")
    return path.read_text(encoding="utf-8"), version


def build_prompt(name: str, variables: dict[str, Any], version: str = "v1") -> tuple[str, str]:
    """Load and render a prompt template; returns (rendered_text, prompt_version)."""
    template, ver = load_prompt(name, version)
    rendered = _render(template, variables)
    for token in ("{{", "}}"):
        if token in rendered:
            logger.warning("prompt %s_%s has unresolved placeholder", name, version)
            break
    return rendered, ver
