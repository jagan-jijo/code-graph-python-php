from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
import json


class BaseModelAdapter(ABC):
    @abstractmethod
    async def health_check(self) -> bool: ...
    @abstractmethod
    async def list_models(self) -> list[str]: ...
    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], model: str,
                   temperature: float = 0.2, max_tokens: int = 2048) -> str: ...

    async def structured_extract(self, prompt: str, schema: dict[str, Any], model: str) -> dict[str, Any]:
        schema_block = json.dumps(schema, indent=2)
        response = await self.chat(
            [{
                "role": "user",
                "content": (
                    f"Return JSON only for this task.\nSchema:\n{schema_block}\n\n"
                    f"Task:\n{prompt}"
                ),
            }],
            model,
        )
        try:
            return json.loads(response.strip().strip("```json").strip("```"))
        except Exception:
            return {"raw": response}

    async def summarize_symbol(self, symbol_context: dict[str, Any], model: str) -> str:
        prompt = (
            f"Briefly summarise the purpose of this {symbol_context.get('type','symbol')} "
            f"named `{symbol_context.get('name','unknown')}` in one or two sentences.\n"
            f"Signature: {symbol_context.get('signature','N/A')}\n"
            f"Docstring: {symbol_context.get('docstring','None')}\n"
            f"Called by: {', '.join(symbol_context.get('callers',[])[:5]) or 'none'}\n"
            f"Calls: {', '.join(symbol_context.get('callees',[])[:5]) or 'none'}\n"
        )
        return await self.chat([{"role": "user", "content": prompt}], model)

    async def infer_edge_classification(self, caller: str, callee: str, snippet: str, model: str) -> dict[str, Any]:
        prompt = (
            f"Analyse this call in `{caller}` to `{callee}`.\n\nCode snippet:\n```\n{snippet[:800]}\n```\n\n"
            "Respond in JSON: {\"likely_target\": \"...\", \"confidence\": 0.0-1.0, \"reasoning\": \"...\"}"
        )
        raw = await self.chat([{"role": "user", "content": prompt}], model)
        try:
            return json.loads(raw.strip().strip("```json").strip("```"))
        except Exception:
            return {"likely_target": callee, "confidence": 0.3, "reasoning": raw[:200]}
