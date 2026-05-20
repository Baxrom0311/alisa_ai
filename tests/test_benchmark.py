"""Tests for benchmark utility."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from alisa.services.benchmark import AlisaBenchmark, get_benchmark


class TestAlisaBenchmark:
    """Test benchmark functionality."""
    
    @pytest.fixture
    def benchmark(self):
        """Create benchmark instance."""
        return AlisaBenchmark()
    
    @pytest.mark.asyncio
    async def test_llm_benchmark(self, benchmark):
        """Test LLM performance benchmark."""
        with patch('alisa.services.benchmark.async_generate') as mock_generate:
            mock_generate.return_value = "Test response"
            
            results = await benchmark.run_llm_benchmark(iterations=1)
            
            assert results["total_requests"] == 5  # 5 test prompts
            assert results["successful_requests"] == 5
            assert results["failed_requests"] == 0
            assert len(results["response_times"]) == 5
            assert results["avg_response_time"] > 0
            assert results["min_response_time"] > 0
            assert results["max_response_time"] > 0
    
    @pytest.mark.asyncio
    async def test_llm_benchmark_with_failures(self, benchmark):
        """Test LLM benchmark with some failures."""
        with patch('alisa.services.benchmark.async_generate') as mock_generate:
            # First call succeeds, second fails, third returns empty
            mock_generate.side_effect = [
                "Good response",
                Exception("API error"),
                "",
                "Another good response",
                "Final response"
            ]
            
            results = await benchmark.run_llm_benchmark(iterations=1)
            
            assert results["total_requests"] == 5
            assert results["successful_requests"] == 3  # 3 good responses
            assert results["failed_requests"] == 2  # 1 exception + 1 empty
            assert len(results["errors"]) == 2
    
    @pytest.mark.asyncio
    async def test_system_benchmark(self, benchmark):
        """Test system performance benchmark."""
        mock_stats = {
            "cpu_percent": 25.0,
            "memory_percent": 60.0,
            "temperature_c": 45.0,
            "disk_percent": 30.0
        }
        
        with patch('alisa.services.benchmark.get_system_stats', return_value=mock_stats):
            results = await benchmark.run_system_benchmark()
            
            assert "avg_cpu_percent" in results
            assert "avg_memory_percent" in results
            assert "max_cpu_percent" in results
            assert "min_memory_percent" in results
            assert results["avg_cpu_percent"] == 25.0
            assert results["avg_memory_percent"] == 60.0
    
    @pytest.mark.asyncio
    async def test_memory_stress_test(self, benchmark):
        """Test memory stress test."""
        mock_stats = {"memory_percent": 55.0}  # Single consistent value
        
        with patch('alisa.services.benchmark.get_system_stats', return_value=mock_stats):
            results = await benchmark.run_memory_stress_test(duration_seconds=1)
            
            assert results["duration_seconds"] == 1
            assert results["memory_samples"] > 0
            assert results["avg_memory_percent"] == 55.0
            assert results["peak_memory_percent"] == 55.0
            assert results["memory_stable"] is True  # Under 90%
    
    @pytest.mark.asyncio
    async def test_memory_stress_test_unstable(self, benchmark):
        """Test memory stress test with high memory usage."""
        mock_stats = {"memory_percent": 95.0}  # High memory usage
        
        with patch('alisa.services.benchmark.get_system_stats', return_value=mock_stats):
            results = await benchmark.run_memory_stress_test(duration_seconds=1)
            
            assert results["peak_memory_percent"] == 95.0
            assert results["memory_stable"] is False  # Over 90%
    
    @pytest.mark.asyncio
    async def test_full_benchmark(self, benchmark):
        """Test full benchmark suite."""
        # Mock all dependencies
        mock_llm_results = {
            "total_requests": 15,
            "successful_requests": 14,
            "failed_requests": 1,
            "avg_response_time": 2.5,
            "response_times": [2.0, 2.5, 3.0]
        }
        
        mock_sys_results = {
            "avg_cpu_percent": 30.0,
            "avg_memory_percent": 50.0
        }
        
        mock_mem_results = {
            "memory_stable": True,
            "peak_memory_percent": 65.0
        }
        
        mock_system_stats = {
            "cpu_percent": 25.0,
            "memory_percent": 45.0,
            "temperature_c": 40.0
        }
        
        with patch.object(benchmark, 'run_llm_benchmark', return_value=mock_llm_results), \
             patch.object(benchmark, 'run_system_benchmark', return_value=mock_sys_results), \
             patch.object(benchmark, 'run_memory_stress_test', return_value=mock_mem_results), \
             patch('alisa.services.benchmark.get_system_stats', return_value=mock_system_stats):
            
            results = await benchmark.run_full_benchmark()
            
            assert "timestamp" in results
            assert "system_info" in results
            assert "llm_performance" in results
            assert "system_performance" in results
            assert "memory_stress" in results
            assert "benchmark_score" in results
            
            score = results["benchmark_score"]
            assert "overall" in score
            assert "llm_score" in score
            assert "system_score" in score
            assert "memory_score" in score
            assert 0 <= score["overall"] <= 100
    
    def test_format_benchmark_report(self, benchmark):
        """Test benchmark report formatting."""
        mock_results = {
            "benchmark_score": {
                "overall": 85.5,
                "llm_score": 35.0,
                "system_score": 25.0,
                "memory_score": 25.5
            },
            "llm_performance": {
                "successful_requests": 14,
                "total_requests": 15,
                "avg_response_time": 2.3,
                "min_response_time": 1.8,
                "max_response_time": 3.1
            },
            "system_performance": {
                "avg_cpu_percent": 28.5,
                "avg_memory_percent": 55.2,
                "max_memory_percent": 62.1
            },
            "memory_stress": {
                "duration_seconds": 30,
                "peak_memory_percent": 68.5,
                "memory_stable": True
            }
        }
        
        report = benchmark.format_benchmark_report(mock_results)
        
        assert "Alisa Performance Benchmark Report" in report
        assert "Overall Score: 85.5/100" in report
        assert "Excellent performance" in report
        assert "Success Rate: 14/15" in report
        assert "Avg Response Time: 2.30s" in report
        assert "Avg CPU: 28.5%" in report
        assert "Peak Memory: 68.5%" in report
        assert "Stable: ✅" in report
    
    def test_format_benchmark_report_poor_performance(self, benchmark):
        """Test benchmark report with poor performance."""
        mock_results = {
            "benchmark_score": {
                "overall": 45.0,
                "llm_score": 15.0,
                "system_score": 15.0,
                "memory_score": 15.0
            },
            "llm_performance": {
                "successful_requests": 8,
                "total_requests": 15,
                "avg_response_time": 8.5,
                "min_response_time": 5.0,
                "max_response_time": 12.0
            },
            "system_performance": {
                "avg_cpu_percent": 85.0,
                "avg_memory_percent": 88.0,
                "max_memory_percent": 92.0
            },
            "memory_stress": {
                "duration_seconds": 30,
                "peak_memory_percent": 95.0,
                "memory_stable": False
            }
        }
        
        report = benchmark.format_benchmark_report(mock_results)
        
        assert "Overall Score: 45.0/100" in report
        assert "Performance issues detected" in report
        assert "Consider upgrading to Raspberry Pi 5" in report
        assert "LLM responses are slow" in report
        assert "High memory usage detected" in report
    
    def test_get_benchmark_singleton(self):
        """Test benchmark singleton pattern."""
        benchmark1 = get_benchmark()
        benchmark2 = get_benchmark()
        
        assert benchmark1 is benchmark2
        assert isinstance(benchmark1, AlisaBenchmark)
    
    @pytest.mark.asyncio
    async def test_benchmark_error_handling(self, benchmark):
        """Test benchmark error handling."""
        with patch('alisa.services.benchmark.async_generate', side_effect=Exception("Connection error")):
            results = await benchmark.run_llm_benchmark(iterations=1)
            
            assert results["total_requests"] == 5
            assert results["successful_requests"] == 0
            assert results["failed_requests"] == 5
            assert len(results["errors"]) == 5
            assert all("Connection error" in error for error in results["errors"])
    
    @pytest.mark.asyncio
    async def test_benchmark_memory_cleanup(self, benchmark):
        """Test that benchmark cleans up memory properly."""
        with patch('alisa.services.benchmark.get_system_stats', return_value={"memory_percent": 50.0}):
            # Run stress test
            results = await benchmark.run_memory_stress_test(duration_seconds=1)
            
            # Should complete without memory issues
            assert results["duration_seconds"] == 1
            assert "avg_memory_percent" in results
    
    def test_benchmark_score_calculation(self, benchmark):
        """Test benchmark score calculation edge cases."""
        # Test with zero successful requests
        mock_results = {
            "benchmark_score": {"overall": 0},
            "llm_performance": {
                "successful_requests": 0,
                "total_requests": 15,
                "avg_response_time": 0
            },
            "system_performance": {
                "avg_cpu_percent": 50.0,
                "avg_memory_percent": 50.0
            },
            "memory_stress": {
                "memory_stable": True
            }
        }
        
        report = benchmark.format_benchmark_report(mock_results)
        assert "Success Rate: 0/15" in report
