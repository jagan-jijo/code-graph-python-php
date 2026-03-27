from __future__ import annotations
import httpx

from ai.base import BaseModelAdapter


class OllamaNativeAdapter(BaseModelAdapter):
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(f"{self.base_url}/api/tags", headers=self._headers())
                return response.is_success
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(f"{self.base_url}/api/tags", headers=self._headers())
            response.raise_for_status()
        payload = response.json()
        return [item.get("name", "") for item in payload.get("models", []) if item.get("name")]

    async def chat(self, messages: list[dict[str, str]], model: str,
                   temperature: float = 0.2, max_tokens: int = 2048) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
        data = response.json()
        message = data.get("message") or {}
        return message.get("content", "")