"""Anthropic Claude provider implementation."""

import os
import httpx
from typing import Optional

from .base import LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider."""
    
    def __init__(self, config):
        super().__init__(config)
        self.api_key = os.environ.get("CLAUDE_API_KEY", self.api_key)
        self.base_url = "https://api.anthropic.com/v1"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response using Claude API."""
        if not self.api_key:
            raise ValueError("Claude API key not configured")
        
        messages = [{"role": "user", "content": prompt}]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 150,
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            return data["content"][0]["text"].strip()
