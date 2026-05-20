"""Performance benchmark utility for Alisa AI Assistant."""

import asyncio
import time
from typing import Dict, List, Any
import structlog

from alisa.brain.llm_manager import get_llm_manager
from alisa.services.health import get_system_stats
from alisa.core.config import get_config

logger = structlog.get_logger()


class AlisaBenchmark:
    """Performance benchmark utility for Pi optimization."""
    
    def __init__(self):
        self.config = get_config()
        self.results: Dict[str, Any] = {}
    
    async def run_llm_benchmark(self, iterations: int = 5) -> Dict[str, Any]:
        """Benchmark LLM response times."""
        logger.info("llm_benchmark_start", iterations=iterations)
        
        test_prompts = [
            "Salom",
            "Bugun ob-havo qanday?",
            "Menga yordam bering",
            "Vaqt necha bo'ldi?",
            "Rahmat"
        ]
        
        results = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "response_times": [],
            "avg_response_time": 0.0,
            "min_response_time": float('inf'),
            "max_response_time": 0.0,
            "errors": []
        }
        
        for i in range(iterations):
            for prompt in test_prompts:
                start_time = time.time()
                results["total_requests"] += 1
                
                try:
                    response = await async_generate(
                        prompt, 
                        system_prompt="Qisqa javob bering."
                    )
                    
                    if response and len(response.strip()) > 0:
                        results["successful_requests"] += 1
                        response_time = time.time() - start_time
                        results["response_times"].append(response_time)
                        results["min_response_time"] = min(results["min_response_time"], response_time)
                        results["max_response_time"] = max(results["max_response_time"], response_time)
                    else:
                        results["failed_requests"] += 1
                        results["errors"].append(f"Empty response for: {prompt}")
                        
                except Exception as e:
                    results["failed_requests"] += 1
                    results["errors"].append(f"Error for '{prompt}': {str(e)}")
                
                # Small delay between requests
                await asyncio.sleep(0.1)
        
        if results["response_times"]:
            results["avg_response_time"] = sum(results["response_times"]) / len(results["response_times"])
        else:
            results["min_response_time"] = 0.0
        
        logger.info("llm_benchmark_complete", **{k: v for k, v in results.items() if k != "errors"})
        return results
    
    async def run_system_benchmark(self) -> Dict[str, Any]:
        """Benchmark system performance."""
        logger.info("system_benchmark_start")
        
        # Collect system stats multiple times
        stats_samples = []
        for i in range(10):
            stats = get_system_stats()
            stats_samples.append(stats)
            await asyncio.sleep(0.5)
        
        # Calculate averages
        avg_stats = {}
        for key in stats_samples[0].keys():
            if isinstance(stats_samples[0][key], (int, float)):
                avg_stats[f"avg_{key}"] = sum(sample[key] for sample in stats_samples) / len(stats_samples)
                avg_stats[f"max_{key}"] = max(sample[key] for sample in stats_samples)
                avg_stats[f"min_{key}"] = min(sample[key] for sample in stats_samples)
        
        logger.info("system_benchmark_complete", **avg_stats)
        return avg_stats
    
    async def run_memory_stress_test(self, duration_seconds: int = 30) -> Dict[str, Any]:
        """Run memory stress test to check Pi stability."""
        logger.info("memory_stress_test_start", duration=duration_seconds)
        
        start_time = time.time()
        memory_samples = []
        peak_memory = 0
        
        # Allocate and deallocate memory in chunks
        test_data = []
        
        while time.time() - start_time < duration_seconds:
            # Get current memory usage
            stats = get_system_stats()
            memory_samples.append(stats["memory_percent"])
            peak_memory = max(peak_memory, stats["memory_percent"])
            
            # Allocate some memory (simulate processing)
            chunk = [0] * 10000  # Small chunk to avoid OOM
            test_data.append(chunk)
            
            # Periodically clean up
            if len(test_data) > 100:
                test_data = test_data[-50:]  # Keep only recent chunks
            
            await asyncio.sleep(0.1)
        
        # Clean up
        test_data.clear()
        
        results = {
            "duration_seconds": duration_seconds,
            "memory_samples": len(memory_samples),
            "avg_memory_percent": sum(memory_samples) / len(memory_samples) if memory_samples else 0,
            "peak_memory_percent": peak_memory,
            "memory_stable": peak_memory < 90.0,  # Consider stable if under 90%
        }
        
        logger.info("memory_stress_test_complete", **results)
        return results
    
    async def run_full_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive benchmark suite."""
        logger.info("full_benchmark_start")
        
        results = {
            "timestamp": time.time(),
            "system_info": get_system_stats(),
            "llm_performance": await self.run_llm_benchmark(iterations=3),
            "system_performance": await self.run_system_benchmark(),
            "memory_stress": await self.run_memory_stress_test(duration_seconds=15),
        }
        
        # Calculate overall score (0-100)
        score = 100
        
        # LLM performance (40% of score)
        llm_results = results["llm_performance"]
        if llm_results["successful_requests"] > 0:
            success_rate = llm_results["successful_requests"] / llm_results["total_requests"]
            avg_time = llm_results["avg_response_time"]
            
            # Penalize slow responses (target: <3s)
            time_penalty = max(0, (avg_time - 3.0) * 10)
            llm_score = (success_rate * 40) - time_penalty
        else:
            llm_score = 0
        
        # System performance (30% of score)
        sys_results = results["system_performance"]
        cpu_score = max(0, 30 - sys_results.get("avg_cpu_percent", 100))
        memory_score = max(0, 30 - sys_results.get("avg_memory_percent", 100))
        system_score = (cpu_score + memory_score) / 2
        
        # Memory stability (30% of score)
        mem_results = results["memory_stress"]
        memory_stability_score = 30 if mem_results["memory_stable"] else 10
        
        overall_score = max(0, min(100, llm_score + system_score + memory_stability_score))
        
        results["benchmark_score"] = {
            "overall": round(overall_score, 1),
            "llm_score": round(llm_score, 1),
            "system_score": round(system_score, 1),
            "memory_score": round(memory_stability_score, 1),
        }
        
        logger.info("full_benchmark_complete", score=overall_score)
        return results
    
    def format_benchmark_report(self, results: Dict[str, Any]) -> str:
        """Format benchmark results as human-readable report."""
        report = []
        report.append("🏁 Alisa Performance Benchmark Report")
        report.append("=" * 50)
        
        # Overall score
        score = results.get("benchmark_score", {})
        overall = score.get("overall", 0)
        report.append(f"\n🎯 Overall Score: {overall}/100")
        
        if overall >= 80:
            report.append("✅ Excellent performance")
        elif overall >= 60:
            report.append("⚠️  Good performance with room for improvement")
        else:
            report.append("❌ Performance issues detected")
        
        # LLM Performance
        llm = results.get("llm_performance", {})
        report.append(f"\n🧠 LLM Performance:")
        report.append(f"  Success Rate: {llm.get('successful_requests', 0)}/{llm.get('total_requests', 0)}")
        report.append(f"  Avg Response Time: {llm.get('avg_response_time', 0):.2f}s")
        report.append(f"  Min/Max: {llm.get('min_response_time', 0):.2f}s / {llm.get('max_response_time', 0):.2f}s")
        
        # System Performance
        sys_perf = results.get("system_performance", {})
        report.append(f"\n💻 System Performance:")
        report.append(f"  Avg CPU: {sys_perf.get('avg_cpu_percent', 0):.1f}%")
        report.append(f"  Avg Memory: {sys_perf.get('avg_memory_percent', 0):.1f}%")
        report.append(f"  Peak Memory: {sys_perf.get('max_memory_percent', 0):.1f}%")
        
        # Memory Stability
        mem = results.get("memory_stress", {})
        report.append(f"\n🧪 Memory Stress Test:")
        report.append(f"  Duration: {mem.get('duration_seconds', 0)}s")
        report.append(f"  Peak Memory: {mem.get('peak_memory_percent', 0):.1f}%")
        report.append(f"  Stable: {'✅' if mem.get('memory_stable', False) else '❌'}")
        
        # Recommendations
        report.append(f"\n💡 Recommendations:")
        if overall < 60:
            report.append("  • Consider upgrading to Raspberry Pi 5 for better performance")
            report.append("  • Check for background processes consuming resources")
        if llm.get('avg_response_time', 0) > 5:
            report.append("  • LLM responses are slow - check internet connection")
            report.append("  • Consider using local Ollama model for faster responses")
        if sys_perf.get('avg_memory_percent', 0) > 80:
            report.append("  • High memory usage detected - consider reducing model sizes")
        
        return "\n".join(report)


# Global instance
_benchmark_instance = None


def get_benchmark() -> AlisaBenchmark:
    """Get global benchmark instance."""
    global _benchmark_instance
    if _benchmark_instance is None:
        _benchmark_instance = AlisaBenchmark()
    return _benchmark_instance


async def async_generate(prompt: str, system_prompt: str = None) -> str:
    """Async LLM generation function for testing compatibility."""
    llm_manager = get_llm_manager()
    return await llm_manager.generate(prompt, system_prompt or "Qisqa javob bering.")
