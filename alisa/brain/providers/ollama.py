"""Ollama local provider implementation."""

import httpx
from typing import Optional

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""
    
    def __init__(self, config):
        super().__init__(config)
        self.base_url = self.base_url or "http://localhost:11434"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response using Ollama API."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("response", "").strip()
    
    def is_available(self) -> bool:
        """Ollama doesn't need API key."""
        return True
