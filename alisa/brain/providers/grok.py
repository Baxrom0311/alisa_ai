"""xAI Grok provider implementation."""

import os
import httpx
from typing import Optional

from .base import LLMProvider


class GrokProvider(LLMProvider):
    """xAI Grok provider."""
    
    def __init__(self, config):
        super().__init__(config)
        self.api_key = os.environ.get("GROK_API_KEY", self.api_key)
        self.base_url = self.base_url or "https://api.x.ai/v1"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response using Grok API."""
        if not self.api_key:
            raise ValueError("Grok API key not configured")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.7,
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
