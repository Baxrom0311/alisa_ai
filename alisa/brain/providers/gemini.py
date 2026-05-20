"""Google Gemini provider implementation."""

import os
import httpx
from typing import Optional

from .base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""
    
    def __init__(self, config):
        super().__init__(config)
        self.api_key = os.environ.get("GEMINI_API_KEY", self.api_key)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response using Gemini API."""
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        
        # Combine system and user prompts
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        payload = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "generationConfig": {
                "maxOutputTokens": 150,
                "temperature": 0.7,
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}",
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
