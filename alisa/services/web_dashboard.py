"""Simple web dashboard for Alisa health monitoring."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import structlog
from aiohttp import web, web_response

from alisa.services.health import get_system_stats, is_system_healthy, get_cpu_temperature
from alisa.brain.llm_manager import get_llm_manager
from alisa.core.config import get_config
from alisa.services.performance_monitor import get_performance_monitor

logger = structlog.get_logger()


class AlisaWebDashboard:
    """Simple web dashboard for monitoring Alisa health."""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.app = web.Application()
        self.llm_manager = get_llm_manager()
        self.config = get_config()
        self.performance_monitor = get_performance_monitor()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup web routes."""
        self.app.router.add_get('/', self._dashboard_html)
        self.app.router.add_get('/api/health', self._health_api)
        self.app.router.add_get('/api/providers', self._providers_api)
        self.app.router.add_get('/api/config', self._config_api)
        self.app.router.add_get('/api/performance', self._performance_api)
    
    async def _dashboard_html(self, request) -> web_response.Response:
        """Serve simple HTML dashboard."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Alisa AI Assistant - Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status-good { color: #28a745; }
        .status-warning { color: #ffc107; }
        .status-error { color: #dc3545; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .metric { display: flex; justify-content: space-between; margin: 5px 0; }
        .refresh-btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #0056b3; }
        pre { background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Alisa AI Assistant Dashboard</h1>
        <button class="refresh-btn" onclick="refreshData()">🔄 Refresh</button>
        
        <div class="grid">
            <div class="card">
                <h2>System Health</h2>
                <div id="health-status">Loading...</div>
            </div>
            
            <div class="card">
                <h2>LLM Providers</h2>
                <div id="providers-status">Loading...</div>
            </div>
            
            <div class="card">
                <h2>Performance</h2>
                <div id="performance-status">Loading...</div>
            </div>
            
            <div class="card">
                <h2>Configuration</h2>
                <div id="config-status">Loading...</div>
            </div>
        </div>
    </div>

    <script>
        async function fetchData(endpoint) {
            try {
                const response = await fetch(endpoint);
                return await response.json();
            } catch (error) {
                return { error: error.message };
            }
        }

        function formatMetric(key, value) {
            return `<div class="metric"><span>${key}:</span><span>${value}</span></div>`;
        }

        function getStatusClass(status) {
            if (status === 'healthy' || status === 'available') return 'status-good';
            if (status === 'warning') return 'status-warning';
            return 'status-error';
        }

        async function refreshData() {
            // Health status
            const health = await fetchData('/api/health');
            const healthDiv = document.getElementById('health-status');
            if (health.error) {
                healthDiv.innerHTML = `<div class="status-error">Error: ${health.error}</div>`;
            } else {
                let healthHtml = `<div class="${getStatusClass(health.status)}">${health.status.toUpperCase()}</div>`;
                healthHtml += formatMetric('CPU Usage', `${health.cpu_percent}%`);
                healthHtml += formatMetric('Memory Usage', `${health.memory_percent}%`);
                healthHtml += formatMetric('Disk Usage', `${health.disk_percent}%`);
                if (health.temperature) {
                    healthHtml += formatMetric('Temperature', `${health.temperature}°C`);
                }
                healthHtml += formatMetric('Uptime', health.uptime);
                healthDiv.innerHTML = healthHtml;
            }

            // Providers status
            const providers = await fetchData('/api/providers');
            const providersDiv = document.getElementById('providers-status');
            if (providers.error) {
                providersDiv.innerHTML = `<div class="status-error">Error: ${providers.error}</div>`;
            } else {
                let providersHtml = '';
                for (const [name, info] of Object.entries(providers.providers)) {
                    const statusClass = getStatusClass(info.status);
                    providersHtml += `<div class="metric">
                        <span>${name}:</span>
                        <span class="${statusClass}">${info.status}</span>
                    </div>`;
                }
                providersDiv.innerHTML = providersHtml;
            }

            // Performance status
            const performance = await fetchData('/api/performance?minutes=60');
            const performanceDiv = document.getElementById('performance-status');
            if (performance.error) {
                performanceDiv.innerHTML = `<div class="status-error">Error: ${performance.error}</div>`;
            } else {
                let perfHtml = '';
                const summary = performance.summary;
                perfHtml += formatMetric('Total Operations', summary.total_operations || 0);
                
                if (summary.operations) {
                    const operations = Object.entries(summary.operations);
                    if (operations.length > 0) {
                        perfHtml += '<h4>Operation Performance:</h4>';
                        for (const [opName, opStats] of operations.slice(0, 5)) {
                            perfHtml += `<div class="metric">
                                <span>${opName}:</span>
                                <span>${opStats.avg_duration_ms.toFixed(0)}ms avg</span>
                            </div>`;
                        }
                    }
                }
                
                if (performance.slow_operations && performance.slow_operations.length > 0) {
                    perfHtml += '<h4>Recent Slow Operations:</h4>';
                    for (const slowOp of performance.slow_operations.slice(0, 3)) {
                        perfHtml += `<div class="metric">
                            <span>${slowOp.name}:</span>
                            <span class="status-warning">${slowOp.duration_ms.toFixed(0)}ms</span>
                        </div>`;
                    }
                }
                
                performanceDiv.innerHTML = perfHtml || '<div>No performance data available</div>';
            }

            // Config status
            const config = await fetchData('/api/config');
            const configDiv = document.getElementById('config-status');
            if (config.error) {
                configDiv.innerHTML = `<div class="status-error">Error: ${config.error}</div>`;
            } else {
                let configHtml = formatMetric('Language', config.language);
                configHtml += formatMetric('Wake Word', config.wake_word);
                configHtml += formatMetric('STT Model', config.stt_model);
                configHtml += formatMetric('TTS Model', config.tts_model);
                configHtml += formatMetric('Providers Count', config.providers_count);
                configDiv.innerHTML = configHtml;
            }
        }

        // Auto-refresh every 30 seconds
        setInterval(refreshData, 30000);
        
        // Initial load
        refreshData();
    </script>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def _health_api(self, request) -> web_response.Response:
        """Health status API endpoint."""
        try:
            stats = get_system_stats()
            health_data = {
                "status": "healthy" if is_system_healthy() else "warning",
                "cpu_percent": stats["cpu_percent"],
                "memory_percent": stats["memory_percent"],
                "disk_percent": stats["disk_percent"],
                "uptime": f"{stats['uptime_hours']:.1f} hours"
            }
            
            # Add temperature if available
            try:
                temp = get_cpu_temperature()
                if temp > 0:
                    health_data["temperature"] = temp
            except:
                pass
            
            return web.json_response(health_data)
        except Exception as e:
            logger.error("dashboard_health_error", error=str(e))
            return web.json_response({"error": str(e)}, status=500)
    
    async def _providers_api(self, request) -> web_response.Response:
        """LLM providers status API endpoint."""
        try:
            providers_data = {
                "providers": {},
                "last_successful": self.llm_manager.last_successful_provider
            }
            
            for provider in self.llm_manager.providers:
                providers_data["providers"][provider.name] = {
                    "status": "available" if provider.is_available() else "unavailable",
                    "model": getattr(provider, 'model', 'unknown')
                }
            
            return web.json_response(providers_data)
        except Exception as e:
            logger.error("dashboard_providers_error", error=str(e))
            return web.json_response({"error": str(e)}, status=500)
    
    async def _config_api(self, request) -> web_response.Response:
        """Configuration API endpoint (without secrets)."""
        try:
            config_data = {
                "language": self.config.get("language", "uz"),
                "wake_word": self.config.get("wake_word", "alisa"),
                "stt_model": self.config.get("stt", {}).get("model", "tiny"),
                "tts_model": self.config.get("tts", {}).get("model", "uz_UZ-doniyorbek-medium"),
                "providers_count": len(self.config.get("llm", {}).get("providers", []))
            }
            return web.json_response(config_data)
        except Exception as e:
            logger.error("dashboard_config_error", error=str(e))
            return web.json_response({"error": str(e)}, status=500)
    
    async def _performance_api(self, request) -> web_response.Response:
        """Performance monitoring API endpoint."""
        try:
            # Get query parameters
            minutes = int(request.query.get('minutes', 60))
            
            # Get performance summary
            summary = await self.performance_monitor.get_summary(last_minutes=minutes)
            
            # Get slow operations
            slow_ops = await self.performance_monitor.get_slow_operations(threshold_ms=3000)
            
            performance_data = {
                "summary": summary,
                "slow_operations": [
                    {
                        "name": op.name,
                        "duration_ms": op.duration_ms,
                        "timestamp": op.timestamp,
                        "success": op.success,
                        "error": op.error
                    }
                    for op in slow_ops[-10:]  # Last 10 slow operations
                ]
            }
            
            return web.json_response(performance_data)
        except Exception as e:
            logger.error("dashboard_performance_error", error=str(e))
            return web.json_response({"error": str(e)}, status=500)
    
    async def start(self):
        """Start the web dashboard."""
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            
            logger.info("web_dashboard_started", port=self.port)
            return runner
        except Exception as e:
            logger.error("web_dashboard_start_error", error=str(e))
            raise
    
    async def stop(self, runner):
        """Stop the web dashboard."""
        try:
            await runner.cleanup()
            logger.info("web_dashboard_stopped")
        except Exception as e:
            logger.error("web_dashboard_stop_error", error=str(e))


# Global instance
_dashboard = None


def get_web_dashboard(port: int = 8080) -> AlisaWebDashboard:
    """Get web dashboard instance."""
    global _dashboard
    if _dashboard is None:
        _dashboard = AlisaWebDashboard(port=port)
    return _dashboard


async def main():
    """Test the web dashboard."""
    dashboard = get_web_dashboard()
    runner = await dashboard.start()
    
    print(f"Dashboard running at http://localhost:8080")
    print("Press Ctrl+C to stop...")
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
        await dashboard.stop(runner)


if __name__ == "__main__":
    asyncio.run(main())
