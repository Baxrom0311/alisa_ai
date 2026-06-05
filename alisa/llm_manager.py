"""Multi-provider LLM manager with fallback chain and sentence streaming."""
import asyncio
import json
import aiohttp
from typing import AsyncGenerator, Optional
from .utils import load_config, save_config


async def _stream_openai_compatible(base_url: str, api_key: str, model: str, messages: list, timeout: int) -> AsyncGenerator[str, None]:
    """Stream from any OpenAI-compatible API (OpenAI, DeepSeek, Grok)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": True}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return
            async for line in resp.content:
                line = line.decode().strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if token:
                    yield token


async def _stream_gemini(api_key: str, model: str, messages: list, timeout: int) -> AsyncGenerator[str, None]:
    """Stream from Google Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        if m["role"] == "system":
            contents.insert(0, {"role": "user", "parts": [{"text": m["content"]}]})
            continue
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"contents": contents}, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return
            async for line in resp.content:
                line = line.decode().strip()
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    yield text


async def _stream_claude(api_key: str, model: str, messages: list, timeout: int) -> AsyncGenerator[str, None]:
    """Stream from Anthropic Claude API."""
    headers = {"x-api-key": api_key, "content-type": "application/json", "anthropic-version": "2023-06-01"}
    system = ""
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            msgs.append(m)
    payload = {"model": model, "messages": msgs, "max_tokens": 1024, "stream": True}
    if system:
        payload["system"] = system
    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return
            async for line in resp.content:
                line = line.decode().strip()
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])
                if data.get("type") == "content_block_delta":
                    text = data.get("delta", {}).get("text", "")
                    if text:
                        yield text


async def _stream_ollama(base_url: str, model: str, messages: list, timeout: int) -> AsyncGenerator[str, None]:
    """Stream from local Ollama."""
    payload = {"model": model, "messages": messages, "stream": True}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/api/chat", json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return
            async for line in resp.content:
                chunk = line.decode().strip()
                if not chunk:
                    continue
                data = json.loads(chunk)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token


def _get_stream(provider: dict, messages: list, timeout: int) -> Optional[AsyncGenerator[str, None]]:
    """Get stream generator for a provider. Returns None if provider can't be used."""
    name = provider["name"]
    api_key = provider.get("api_key", "")
    model = provider["model"]

    if name == "ollama":
        base_url = provider.get("base_url", "http://localhost:11434")
        return _stream_ollama(base_url, model, messages, timeout)

    # All other providers need API key
    if not api_key:
        return None

    if name in ("openai", "deepseek", "grok"):
        base_url = provider.get("base_url", "https://api.openai.com/v1")
        return _stream_openai_compatible(base_url, api_key, model, messages, timeout)
    elif name == "gemini":
        return _stream_gemini(api_key, model, messages, timeout)
    elif name == "claude":
        return _stream_claude(api_key, model, messages, timeout)
    return None


async def stream_llm(messages: list) -> AsyncGenerator[str, None]:
    """Stream LLM response with fallback chain. Yields tokens."""
    config = load_config()
    llm_cfg = config["llm"]
    providers = llm_cfg["providers"]
    timeout = llm_cfg.get("timeout_sec", 5)
    local_timeout = llm_cfg.get("local_timeout_sec", 10)
    last = llm_cfg.get("last_provider")

    # Reorder: put last successful provider first
    if last:
        providers = sorted(providers, key=lambda p: p["name"] != last)

    for provider in providers:
        t = local_timeout if provider["name"] == "ollama" else timeout
        gen = _get_stream(provider, messages, t)
        if gen is None:
            continue
        try:
            got_any = False
            async for token in gen:
                got_any = True
                yield token
            if got_any:
                # Remember successful provider
                if provider["name"] != last:
                    config["llm"]["last_provider"] = provider["name"]
                    save_config(config)
                return
        except (asyncio.TimeoutError, aiohttp.ClientError, Exception):
            continue

    yield "Kechirasiz, hozir javob bera olmayapman."


async def generate_sentences(messages: list) -> AsyncGenerator[str, None]:
    """Stream LLM and yield complete sentences for TTS."""
    buffer = ""
    async for token in stream_llm(messages):
        buffer += token
        while any(p in buffer for p in ".!?\n"):
            for i, ch in enumerate(buffer):
                if ch in ".!?\n":
                    sentence = buffer[:i + 1].strip()
                    buffer = buffer[i + 1:]
                    if sentence and len(sentence) > 1:
                        yield sentence
                    break
    if buffer.strip():
        yield buffer.strip()
