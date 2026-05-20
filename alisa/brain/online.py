"""Online features: weather, news, online LLM fallback.

Weather API uses Open-Meteo (https://api.open-meteo.com/v1/forecast) - 
a free, keyless weather API that provides current weather and forecasts.
"""

import asyncio
import httpx
import structlog
import time
from typing import Optional

from alisa.core.config import get_config

logger = structlog.get_logger()

# Shared HTTP client for reuse
_http_client: Optional[httpx.AsyncClient] = None

# Cache for online status with 30-second TTL
_online_cache = {"status": None, "timestamp": 0}
_CACHE_TTL = 30.0

# City coordinates for weather lookup
CITY_COORDINATES = {
    "tashkent": (41.2995, 69.2401),
    "samarqand": (39.6270, 66.9750),
    "buxoro": (39.7747, 64.4286),
    "namangan": (40.9983, 71.6726),
    "andijon": (40.7821, 72.3442),
    "farg'ona": (40.3842, 71.7843),
    "qarshi": (38.8606, 65.7890),
    "termiz": (37.2242, 67.2783),
    "nukus": (42.4531, 59.6103),
    "urganch": (41.5500, 60.6333),
}


def _get_http_client() -> httpx.AsyncClient:
    """Get or create shared HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0))
    return _http_client


async def aclose():
    """Close the shared HTTP client."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def _probe() -> bool:
    """Probe internet connectivity with fast TCP/HTTPS check."""
    try:
        client = _get_http_client()
        resp = await client.get("https://www.cloudflare.com/cdn-cgi/trace", follow_redirects=True, timeout=1.0)
        return resp.status_code < 400
    except Exception:
        return False


def is_online() -> bool:
    """Check if internet connection is available (sync version)."""
    try:
        resp = httpx.get("https://www.cloudflare.com/cdn-cgi/trace", follow_redirects=True, timeout=1.0)
        return resp.status_code < 400
    except Exception:
        return False


async def async_is_online() -> bool:
    """Async check if internet connection is available with 30s TTL cache."""
    global _online_cache
    
    now = time.monotonic()
    if now - _online_cache["timestamp"] < _CACHE_TTL and _online_cache["status"] is not None:
        return _online_cache["status"]
    
    # Cache miss or expired - probe connectivity
    status = await _probe()
    _online_cache = {"status": status, "timestamp": now}
    return status


def get_weather(city: str = "Tashkent") -> Optional[str]:
    """Get weather information for a city using Open-Meteo API."""
    if not is_online():
        return None
    
    try:
        # Normalize city name
        city_key = city.lower().replace("'", "'")
        
        if city_key not in CITY_COORDINATES:
            logger.warning("weather_city_not_found", city=city)
            return None
        
        lat, lon = CITY_COORDINATES[city_key]
        
        # Call Open-Meteo API
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "Asia/Tashkent"
        }
        
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        
        current = data.get("current", {})
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_speed = current.get("wind_speed_10m")
        weather_code = current.get("weather_code")
        
        if temp is None:
            logger.error("weather_api_invalid_response", data=data)
            return None
        
        # Format weather description based on WMO weather codes
        weather_desc = _get_weather_description(weather_code)
        
        # Format response in Uzbek
        response = f"{city}da hozirgi ob-havo: {temp}°C, {weather_desc}"
        if humidity:
            response += f", namlik {humidity}%"
        if wind_speed:
            response += f", shamol tezligi {wind_speed} km/soat"
        
        logger.info("weather_fetched", city=city, temp=temp)
        return response
        
    except Exception as e:
        logger.error("weather_error", error=str(e), city=city)
        return None


def _get_weather_description(weather_code: Optional[int]) -> str:
    """Convert WMO weather code to Uzbek description."""
    if weather_code is None:
        return "noma'lum"
    
    # WMO Weather interpretation codes
    weather_descriptions = {
        0: "ochiq osmon",
        1: "asosan ochiq",
        2: "qisman bulutli", 
        3: "bulutli",
        45: "tumanli",
        48: "muzli tuman",
        51: "engil yomg'ir",
        53: "o'rtacha yomg'ir",
        55: "kuchli yomg'ir",
        61: "yengil yomg'ir",
        63: "o'rtacha yomg'ir",
        65: "kuchli yomg'ir",
        71: "yengil qor",
        73: "o'rtacha qor",
        75: "kuchli qor",
        80: "yomg'ir yog'adi",
        81: "kuchli yomg'ir",
        82: "juda kuchli yomg'ir",
        95: "momaqaldiroq",
        96: "momaqaldiroq va do'l",
        99: "kuchli momaqaldiroq"
    }
    
    return weather_descriptions.get(weather_code, "noma'lum ob-havo")


def get_news() -> Optional[str]:
    """Get latest news headlines."""
    if not is_online():
        return None
    
    try:
        # Mock news response for demo
        logger.info("news_requested")
        return "Bugungi yangiliklar: Texnologiya sohasida yangi yutuqlar, iqtisodiyot barqaror o'sishda davom etmoqda."
        
    except Exception as e:
        logger.error("news_error", error=str(e))
        return None


def online_llm_fallback(prompt: str, system_prompt: str = None) -> Optional[str]:
    """Fallback to online LLM when local model fails."""
    if not is_online():
        return None
    
    cfg = get_config()
    openai_key = cfg.get("openai", {}).get("api_key")
    
    if not openai_key:
        logger.warning("no_openai_key")
        return None
    
    try:
        headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.7
        }
        
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10.0
        )
        resp.raise_for_status()
        
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        
        logger.info("online_llm_success", model="gpt-3.5-turbo")
        return content
        
    except Exception as e:
        logger.error("online_llm_error", error=str(e))
        return None


def handle_special_queries(text: str) -> Optional[str]:
    """Handle special online queries like weather and news."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["ob-havo", "weather", "harorat"]):
        return get_weather()
    
    if any(word in text_lower for word in ["yangilik", "news", "xabar"]):
        return get_news()
    
    return None


# Async variants using httpx.AsyncClient


async def async_get_weather(city: str = "Tashkent") -> Optional[str]:
    """Async get weather information for a city using Open-Meteo API."""
    if not await async_is_online():
        return None
    
    try:
        # Normalize city name
        city_key = city.lower().replace("'", "'")
        
        if city_key not in CITY_COORDINATES:
            logger.warning("weather_city_not_found", city=city)
            return None
        
        lat, lon = CITY_COORDINATES[city_key]
        
        # Call Open-Meteo API
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "Asia/Tashkent"
        }
        
        client = _get_http_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        current = data.get("current", {})
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_speed = current.get("wind_speed_10m")
        weather_code = current.get("weather_code")
        
        if temp is None:
            logger.error("weather_api_invalid_response", data=data)
            return None
        
        # Format weather description based on WMO weather codes
        weather_desc = _get_weather_description(weather_code)
        
        # Format response in Uzbek
        response = f"{city}da hozirgi ob-havo: {temp}°C, {weather_desc}"
        if humidity:
            response += f", namlik {humidity}%"
        if wind_speed:
            response += f", shamol tezligi {wind_speed} km/soat"
        
        logger.info("weather_fetched", city=city, temp=temp)
        return response
        
    except Exception as e:
        logger.error("weather_error", error=str(e), city=city)
        return None


async def async_get_news() -> Optional[str]:
    """Async get latest news headlines."""
    if not await async_is_online():
        return None
    
    try:
        # Mock news response for demo
        logger.info("news_requested")
        return "Bugungi yangiliklar: Texnologiya sohasida yangi yutuqlar, iqtisodiyot barqaror o'sishda davom etmoqda."
        
    except Exception as e:
        logger.error("news_error", error=str(e))
        return None


async def async_online_llm_fallback(prompt: str, system_prompt: str = None) -> Optional[str]:
    """Async fallback to online LLM when local model fails."""
    if not await async_is_online():
        return None
    
    cfg = get_config()
    openai_key = cfg.get("openai", {}).get("api_key")
    
    if not openai_key:
        logger.warning("no_openai_key")
        return None
    
    try:
        headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.7
        }
        
        client = _get_http_client()
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        resp.raise_for_status()
        
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        
        logger.info("online_llm_success", model="gpt-3.5-turbo")
        return content
        
    except Exception as e:
        logger.error("online_llm_error", error=str(e))
        return None


async def async_handle_special_queries(text: str) -> Optional[str]:
    """Async handle special online queries like weather and news."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["ob-havo", "weather", "harorat"]):
        return await async_get_weather()
    
    if any(word in text_lower for word in ["yangilik", "news", "xabar"]):
        return await async_get_news()
    
    return None
