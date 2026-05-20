"""Multi-LLM fallback chain manager as specified in PROJECT_BRIEF.md."""

import asyncio
import time
from typing import Optional, List, Dict, Any
import structlog

from alisa.core.config import get_config
from alisa.brain.providers.base import LLMProvider
from alisa.brain.providers.openai import OpenAIProvider
from alisa.brain.providers.gemini import GeminiProvider
from alisa.brain.providers.deepseek import DeepSeekProvider
from alisa.brain.providers.grok import GrokProvider
from alisa.brain.providers.claude import ClaudeProvider
from alisa.brain.providers.ollama import OllamaProvider

logger = structlog.get_logger()


class LLMManager:
    """Manages fallback chain across multiple LLM providers."""
    
    def __init__(self):
        self.config = get_config()
        self.providers: List[LLMProvider] = []
        self.last_successful_provider: Optional[str] = None
        self.provider_stats: Dict[str, Dict[str, Any]] = {}
        
        # Promote timeout values to instance attributes for test overridability
        llm_config = self.config.get("llm", {})
        self.timeout_sec = llm_config.get("timeout_sec", 5)
        self.local_timeout_sec = llm_config.get("local_timeout_sec", 10)
        
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize providers based on config."""
        llm_config = self.config.get("llm", {})
        provider_configs = llm_config.get("providers", [])
        
        provider_classes = {
            "openai": OpenAIProvider,
            "gemini": GeminiProvider,
            "deepseek": DeepSeekProvider,
            "grok": GrokProvider,
            "claude": ClaudeProvider,
            "ollama": OllamaProvider,
        }
        
        for provider_config in provider_configs:
            provider_name = provider_config.get("name")
            if provider_name not in provider_classes:
                logger.warning("unknown_provider", name=provider_name)
                continue
            
            # Skip if no API key (except Ollama which doesn't need one)
            if provider_name != "ollama" and not provider_config.get("api_key"):
                logger.debug("provider_skipped_no_key", name=provider_name)
                continue
            
            try:
                provider_class = provider_classes[provider_name]
                provider = provider_class(provider_config)
                self.providers.append(provider)
                
                # Initialize stats
                self.provider_stats[provider_name] = {
                    "requests": 0,
                    "successes": 0,
                    "failures": 0,
                    "avg_response_time": 0.0,
                    "last_used": None,
                    "last_error": None,
                }
                
                logger.info("provider_initialized", name=provider_name)
            except Exception as e:
                logger.error("provider_init_failed", name=provider_name, error=str(e))
        
        if not self.providers:
            logger.error("no_providers_available")
        else:
            logger.info("llm_manager_ready", provider_count=len(self.providers))
    
    def _reorder_providers(self) -> List[LLMProvider]:
        """Reorder providers to start with last successful one."""
        if not self.last_successful_provider:
            return self.providers
        
        # Find last successful provider
        last_provider = None
        other_providers = []
        
        for provider in self.providers:
            if provider.name == self.last_successful_provider:
                last_provider = provider
            else:
                other_providers.append(provider)
        
        if last_provider:
            return [last_provider] + other_providers
        return self.providers
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response using fallback chain."""
        if not self.providers:
            return "Kechirasiz, hech qanday LLM mavjud emas."
        
        ordered_providers = self._reorder_providers()
        
        for provider in ordered_providers:
            provider_name = provider.name
            stats = self.provider_stats[provider_name]
            
            try:
                start_time = time.time()
                stats["requests"] += 1
                
                # Use appropriate timeout from instance attributes
                current_timeout = self.local_timeout_sec if provider_name == "ollama" else self.timeout_sec
                
                logger.debug("trying_provider", name=provider_name, timeout=current_timeout)
                
                # Try to generate with timeout
                response = await asyncio.wait_for(
                    provider.generate(prompt, system_prompt),
                    timeout=current_timeout
                )
                
                if response and response.strip():
                    # Success!
                    response_time = time.time() - start_time
                    stats["successes"] += 1
                    stats["last_used"] = time.time()
                    stats["last_error"] = None
                    
                    # Update average response time
                    if stats["avg_response_time"] == 0:
                        stats["avg_response_time"] = response_time
                    else:
                        stats["avg_response_time"] = (stats["avg_response_time"] + response_time) / 2
                    
                    # Remember successful provider
                    self.last_successful_provider = provider_name
                    
                    logger.info("provider_success", 
                              name=provider_name, 
                              response_time=f"{response_time:.2f}s",
                              response_length=len(response))
                    
                    return response.strip()
                else:
                    logger.warning("provider_empty_response", name=provider_name)
                    stats["failures"] += 1
                    stats["last_error"] = "Empty response"
            
            except asyncio.TimeoutError:
                stats["failures"] += 1
                stats["last_error"] = f"Timeout ({current_timeout}s)"
                logger.warning("provider_timeout", name=provider_name, timeout=current_timeout)
            
            except Exception as e:
                stats["failures"] += 1
                stats["last_error"] = str(e)
                logger.error("provider_error", name=provider_name, error=str(e))
        
        # All providers failed
        logger.error("all_providers_failed", provider_count=len(ordered_providers))
        return "Kechirasiz, javob bera olmadim."
    
    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        status = {
            "active_providers": len(self.providers),
            "last_successful": self.last_successful_provider,
            "providers": {}
        }
        
        for provider in self.providers:
            name = provider.name
            stats = self.provider_stats[name]
            
            success_rate = 0.0
            if stats["requests"] > 0:
                success_rate = (stats["successes"] / stats["requests"]) * 100
            
            status["providers"][name] = {
                "available": True,
                "requests": stats["requests"],
                "success_rate": f"{success_rate:.1f}%",
                "avg_response_time": f"{stats['avg_response_time']:.2f}s",
                "last_used": stats["last_used"],
                "last_error": stats["last_error"],
            }
        
        return status


# Global instance
_llm_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """Get global LLM manager instance."""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager


async def generate_with_fallback(prompt: str, system_prompt: Optional[str] = None) -> str:
    """Generate response using fallback chain."""
    manager = get_llm_manager()
    return await manager.generate(prompt, system_prompt)
