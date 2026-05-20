"""Tests for system optimizer."""

import pytest
import asyncio
from unittest.mock import Mock, patch, mock_open
from alisa.services.optimizer import SystemOptimizer, get_optimizer


class TestSystemOptimizer:
    """Test system optimizer functionality."""
    
    @pytest.fixture
    def optimizer(self):
        """Create optimizer instance."""
        return SystemOptimizer()
    
    def test_optimizer_initialization(self, optimizer):
        """Test optimizer initializes correctly."""
        assert optimizer is not None
        assert len(optimizer.optimizations) == 5
        assert "memory" in optimizer.optimizations
        assert "swap" in optimizer.optimizations
        assert "cpu" in optimizer.optimizations
        assert "disk" in optimizer.optimizations
        assert "network" in optimizer.optimizations
    
    @pytest.mark.asyncio
    async def test_analyze_memory_success(self, optimizer):
        """Test memory analysis with valid data."""
        meminfo_data = """MemTotal:        4096000 kB
MemFree:         1024000 kB
MemAvailable:    2048000 kB
Buffers:          256000 kB
Cached:           512000 kB
SwapCached:            0 kB"""
        
        with patch("builtins.open", mock_open(read_data=meminfo_data)):
            result = await optimizer._analyze_memory()
        
        assert "error" not in result
        assert result["total_mb"] == 4000  # 4096000 / 1024
        assert result["available_mb"] == 2000  # 2048000 / 1024
        assert "usage_percent" in result
        assert "cache_percent" in result
        assert "fragmentation" in result
    
    @pytest.mark.asyncio
    async def test_analyze_memory_error(self, optimizer):
        """Test memory analysis with file error."""
        with patch("builtins.open", side_effect=FileNotFoundError()):
            result = await optimizer._analyze_memory()
        
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_analyze_swap_success(self, optimizer):
        """Test swap analysis with valid data."""
        swaps_data = """Filename				Type		Size	Used	Priority
/swapfile                              	file    	2097148	1048576	-2"""
        
        swappiness_data = "10"
        
        def mock_open_func(filename, *args, **kwargs):
            if "/proc/swaps" in filename:
                return mock_open(read_data=swaps_data)()
            elif "/proc/sys/vm/swappiness" in filename:
                return mock_open(read_data=swappiness_data)()
            else:
                raise FileNotFoundError()
        
        with patch("builtins.open", side_effect=mock_open_func):
            result = await optimizer._analyze_swap()
        
        assert "error" not in result
        assert result["total_mb"] > 0
        assert result["swappiness"] == 10
        assert len(result["swap_files"]) == 1
        assert result["swap_files"][0]["file"] == "/swapfile"
    
    @pytest.mark.asyncio
    async def test_analyze_cpu_success(self, optimizer):
        """Test CPU analysis with valid data."""
        def mock_open_func(filename, *args, **kwargs):
            if "scaling_governor" in filename:
                return mock_open(read_data="ondemand")()
            elif "scaling_available_governors" in filename:
                return mock_open(read_data="ondemand powersave performance")()
            elif "scaling_cur_freq" in filename:
                return mock_open(read_data="1800000")()
            else:
                raise FileNotFoundError()
        
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", side_effect=mock_open_func), \
             patch("os.cpu_count", return_value=4):
            result = await optimizer._analyze_cpu()
        
        assert "error" not in result
        assert result["governor"] == "ondemand"
        assert result["cpu_count"] == 4
        assert result["current_freq_khz"] == 1800000
        assert "ondemand" in result["available_governors"]
    
    @pytest.mark.asyncio
    async def test_analyze_disk_success(self, optimizer):
        """Test disk analysis."""
        with patch("shutil.disk_usage", return_value=(64*1024**3, 32*1024**3, 32*1024**3)), \
             patch("builtins.open", mock_open(read_data="/dev/mmcblk0p2 / ext4 rw")):
            result = await optimizer._analyze_disk()
        
        assert "error" not in result
        assert result["total_gb"] == 64
        assert result["used_gb"] == 32
        assert result["free_gb"] == 32
        assert result["usage_percent"] == 50.0
        assert result["storage_type"] == "sd_card"
    
    @pytest.mark.asyncio
    async def test_analyze_network_success(self, optimizer):
        """Test network analysis."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.iterdir") as mock_iterdir:
            
            # Mock network interfaces
            mock_iface = Mock()
            mock_iface.name = "wlan0"
            mock_iterdir.return_value = [mock_iface]
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.stdout = "wlan0     IEEE 802.11  Power Management:on"
                
                result = await optimizer._analyze_network()
        
        assert "error" not in result
        assert "interfaces" in result
        assert "wifi_power_management" in result
    
    @pytest.mark.asyncio
    async def test_generate_recommendations(self, optimizer):
        """Test recommendation generation."""
        analysis = {
            "memory": {"usage_percent": 85, "cache_percent": 3},
            "swap": {"swappiness": 60, "usage_percent": 60},
            "cpu": {"governor": "powersave"},
            "disk": {"usage_percent": 90, "storage_type": "sd_card"},
            "network": {"wifi_power_management": {"wlan0": "on"}}
        }
        
        recommendations = optimizer._generate_recommendations(analysis)
        
        assert len(recommendations) > 0
        assert any("memory usage" in rec.lower() for rec in recommendations)
        assert any("swappiness" in rec.lower() for rec in recommendations)
        assert any("governor" in rec.lower() for rec in recommendations)
        assert any("disk usage" in rec.lower() for rec in recommendations)
        assert any("power management" in rec.lower() for rec in recommendations)
    
    @pytest.mark.asyncio
    async def test_apply_optimizations_success(self, optimizer):
        """Test applying optimizations."""
        with patch.object(optimizer, "_optimize_memory", return_value={"applied": ["test"]}), \
             patch.object(optimizer, "_optimize_swap", return_value={"applied": ["test"]}):
            
            results = await optimizer.apply_optimizations(["memory", "swap"])
        
        assert "memory" in results
        assert "swap" in results
        assert results["memory"]["status"] == "success"
        assert results["swap"]["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_apply_optimizations_error(self, optimizer):
        """Test optimization error handling."""
        # Create a mock that raises an exception
        async def mock_optimize_memory():
            raise Exception("Test error")
        
        # Replace the method in the optimizations dictionary
        optimizer.optimizations["memory"] = mock_optimize_memory
        
        results = await optimizer.apply_optimizations(["memory"])
        
        assert "memory" in results
        assert results["memory"]["status"] == "error"
        assert "Test error" in results["memory"]["error"]
    
    @pytest.mark.asyncio
    async def test_optimize_memory(self, optimizer):
        """Test memory optimization."""
        with patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open()) as mock_file:
            
            result = await optimizer._optimize_memory()
        
        assert "applied" in result
        mock_run.assert_called_with(["sync"], check=True, timeout=10)
        mock_file.assert_called()
    
    @pytest.mark.asyncio
    async def test_optimize_swap(self, optimizer):
        """Test swap optimization."""
        with patch("builtins.open", mock_open()) as mock_file:
            result = await optimizer._optimize_swap()
        
        assert "applied" in result
        mock_file.assert_called_with("/proc/sys/vm/swappiness", "w")
    
    @pytest.mark.asyncio
    async def test_optimize_cpu(self, optimizer):
        """Test CPU optimization."""
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open()) as mock_file:
            
            result = await optimizer._optimize_cpu()
        
        assert "applied" in result
        mock_file.assert_called()
    
    @pytest.mark.asyncio
    async def test_optimize_disk(self, optimizer):
        """Test disk optimization."""
        result = await optimizer._optimize_disk()
        
        assert "applied" in result
        assert len(result["applied"]) > 0
    
    @pytest.mark.asyncio
    async def test_optimize_network(self, optimizer):
        """Test network optimization."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "wlan0     IEEE 802.11  ESSID:test"
            
            result = await optimizer._optimize_network()
        
        assert "applied" in result
    
    @pytest.mark.asyncio
    async def test_analyze_system_full(self, optimizer):
        """Test full system analysis."""
        with patch.object(optimizer, "_analyze_memory", return_value={"usage_percent": 50}), \
             patch.object(optimizer, "_analyze_swap", return_value={"swappiness": 60}), \
             patch.object(optimizer, "_analyze_cpu", return_value={"governor": "ondemand"}), \
             patch.object(optimizer, "_analyze_disk", return_value={"usage_percent": 30}), \
             patch.object(optimizer, "_analyze_network", return_value={"interfaces": ["eth0"]}):
            
            result = await optimizer.analyze_system()
        
        assert "memory" in result
        assert "swap" in result
        assert "cpu" in result
        assert "disk" in result
        assert "network" in result
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)


def test_get_optimizer():
    """Test global optimizer instance."""
    optimizer1 = get_optimizer()
    optimizer2 = get_optimizer()
    
    assert optimizer1 is not None
    assert optimizer1 is optimizer2  # Should be same instance
    assert isinstance(optimizer1, SystemOptimizer)
