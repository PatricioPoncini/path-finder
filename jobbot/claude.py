"""Wrapper fino sobre el SDK de Anthropic: salida estructurada vía tool use y conteo de uso."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Union

from .config import SetupError

DEFAULT_MODEL = "claude-haiku-5-5"


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0


class ClaudeError(RuntimeError):
    pass


class Claude:
    def __init__(self, model: str = DEFAULT_MODEL):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SetupError(
                "Falta ANTHROPIC_API_KEY. Creá una en https://console.anthropic.com/ y ponela en "
                "el archivo .env (ver .env.example), o usá --no-llm para una búsqueda sin Claude."
            )
        import anthropic  # import tardío: --no-llm no lo necesita

        self.model = model
        self.usage = Usage()
        self._client = anthropic.Anthropic(api_key=key, max_retries=4)

    def tool_call(
        self,
        system: str,
        user: Union[str, List[Dict[str, Any]]],
        tool: Dict[str, Any],
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Fuerza a Claude a responder llamando `tool`; devuelve los argumentos como dict."""
        import anthropic

        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                # Bloque de sistema cacheable: perfil + preferencias se repiten en cada lote
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AuthenticationError as e:
            raise SetupError("La ANTHROPIC_API_KEY no es válida: %s" % e) from e
        except anthropic.NotFoundError as e:
            raise SetupError(
                "El modelo '%s' no existe o no tenés acceso. Cambialo en preferences.yaml (campo "
                "`model`) o con --model. Detalle: %s" % (self.model, e)
            ) from e
        except anthropic.APIError as e:
            raise ClaudeError("Error de la API de Anthropic: %s" % e) from e

        self.usage.add(resp.usage)
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input)
        raise ClaudeError("Claude no devolvió salida estructurada (stop_reason=%s)" % resp.stop_reason)
