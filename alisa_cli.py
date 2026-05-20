#!/usr/bin/env python3
"""Alisa CLI - Quick status and control utility for Raspberry Pi deployment."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from alisa.services.health import get_system_stats, format_system_status, is_system_healthy, check_memory_pressure
from alisa.brain.llm_manager import get_llm_manager
from alisa.core.config import get_config


def status_command():
    """Show system and Alisa status."""
    print("🤖 Alisa AI Assistant - Status")
    print("=" * 40)
    
    # System health
    print("\n📊 System Status:")
    print(format_system_status())
    
    # Health check
    healthy = is_system_healthy()
    health_icon = "✅" if healthy else "⚠️"
    print(f"\n{health_icon} System Health: {'Healthy' if healthy else 'Issues detected'}")
    
    # Memory pressure
    memory_info = check_memory_pressure()
    pressure_icons = {
        "normal": "🟢",
        "moderate": "🟡", 
        "high": "🟠",
        "critical": "🔴",
        "unknown": "❓"
    }
    pressure_icon = pressure_icons.get(memory_info["pressure_level"], "❓")
    print(f"{pressure_icon} Memory Pressure: {memory_info['pressure_level'].title()}")
    
    if memory_info["suggestions"]:
        print("\n💡 Suggestions:")
        for suggestion in memory_info["suggestions"]:
            print(f"  • {suggestion}")


def memory_command():
    """Show memory details and perform cleanup if needed."""
    print("🧠 Memory Management")
    print("=" * 30)
    
    from alisa.core.memory_manager import get_memory_manager
    memory_manager = get_memory_manager()
    
    # Show current memory stats
    stats = memory_manager.get_memory_stats()
    if stats:
        print(f"\n📊 Current Memory Usage:")
        print(f"  • Process RSS: {stats['rss_mb']:.1f} MB")
        print(f"  • Process VMS: {stats['vms_mb']:.1f} MB") 
        print(f"  • Process %: {stats['percent']:.1f}%")
        print(f"  • Available: {stats['available_mb']:.1f} MB")
        print(f"  • GC Objects: {stats['gc_objects']:,}")
        
        # Check if cleanup is needed
        if memory_manager.should_cleanup():
            print(f"\n⚠️ Memory cleanup recommended (>{memory_manager.max_memory_mb * memory_manager.cleanup_threshold:.0f}MB)")
            print("Running cleanup...")
            result = memory_manager.cleanup()
            print(f"✅ Cleanup completed:")
            print(f"  • Objects collected: {result['objects_collected']}")
            print(f"  • Memory freed: {result['memory_freed_mb']:.1f} MB")
        else:
            print(f"\n✅ Memory usage is within normal limits")


async def providers_command():
    """Show LLM provider status."""
    print("🧠 LLM Providers Status")
    print("=" * 40)
    
    manager = get_llm_manager()
    status = manager.get_provider_status()
    
    print(f"\nActive Providers: {status['active_providers']}")
    if status['last_successful']:
        print(f"Last Successful: {status['last_successful']}")
    
    providers = status.get('providers', {})
    if not providers:
        print("\n❌ No providers configured or available")
        return
    
    for provider_name, provider_info in providers.items():
        status_icon = "✅" if provider_info["available"] else "❌"
        print(f"\n{status_icon} {provider_name.title()}")
        print(f"  Available: {provider_info['available']}")
        print(f"  Requests: {provider_info['requests']}")
        print(f"  Success Rate: {provider_info['success_rate']}")
        print(f"  Avg Response: {provider_info['avg_response_time']}")
        
        if provider_info.get("last_error"):
            print(f"  Last Error: {provider_info['last_error']}")
        
        if provider_info.get("last_used"):
            print(f"  Last Used: {provider_info['last_used']}")


def config_command():
    """Show current configuration."""
    print("⚙️ Configuration")
    print("=" * 40)
    
    config = get_config()
    
    # Show key config without sensitive data
    print(f"Language: {config.get('language', 'uz')}")
    print(f"Wake Word: {config.get('wake_word', 'alisa')}")
    
    # LLM config
    llm_config = config.get('llm', {})
    print(f"\nLLM Timeout: {llm_config.get('timeout_sec', 5)}s")
    print(f"Local Timeout: {llm_config.get('local_timeout_sec', 10)}s")
    
    providers = llm_config.get('providers', [])
    print(f"\nConfigured Providers: {len(providers)}")
    for provider in providers:
        name = provider.get('name', 'unknown')
        has_key = bool(provider.get('api_key', '').strip())
        key_status = "✅" if has_key or name == 'ollama' else "❌"
        print(f"  {key_status} {name}: {provider.get('model', 'N/A')}")


async def test_command():
    """Test basic functionality."""
    print("🧪 Testing Alisa Components")
    print("=" * 40)
    
    # Test LLM
    print("\n🧠 Testing LLM...")
    try:
        from alisa.brain.llm_manager import get_llm_manager
        llm_manager = get_llm_manager()
        response = await llm_manager.generate("Salom", system_prompt="Qisqa javob bering.")
        print(f"✅ LLM Response: {response[:50]}...")
    except Exception as e:
        print(f"❌ LLM Error: {e}")
    
    # Test config
    print("\n⚙️ Testing Config...")
    try:
        config = get_config()
        print(f"✅ Config loaded: {len(config)} sections")
    except Exception as e:
        print(f"❌ Config Error: {e}")
    
    print("\n✅ Basic tests completed")


async def benchmark_command():
    """Run performance benchmark."""
    print("🏁 Running Alisa Performance Benchmark")
    print("=" * 40)
    print("This may take 1-2 minutes...")
    
    try:
        from alisa.services.benchmark import get_benchmark
        benchmark = get_benchmark()
        
        results = await benchmark.run_full_benchmark()
        report = benchmark.format_benchmark_report(results)
        
        print("\n" + report)
        
    except Exception as e:
        print(f"❌ Benchmark Error: {e}")
        import traceback
        traceback.print_exc()


async def logs_command():
    """Manage log files and rotation."""
    print("📝 Alisa Log Management")
    print("=" * 30)
    
    try:
        from alisa.services.log_manager import get_log_manager
        from pathlib import Path
        
        log_manager = get_log_manager()
        
        # Get current log statistics
        print("\n📊 Current Log Status:")
        stats = await log_manager.get_log_stats()
        
        if "error" in stats:
            print(f"❌ Error getting log stats: {stats['error']}")
            return
        
        print(f"  Total Files: {stats['total_files']}")
        print(f"  Total Size: {stats['total_size_mb']:.2f} MB")
        print(f"  Current Logs: {len(stats['current_logs'])}")
        print(f"  Archived Logs: {len(stats['archived_logs'])}")
        
        if stats['oldest_file']:
            print(f"  Oldest File: {Path(stats['oldest_file']).name}")
        if stats['newest_file']:
            print(f"  Newest File: {Path(stats['newest_file']).name}")
        
        # Show current log files
        if stats['current_logs']:
            print(f"\n📄 Current Log Files:")
            for log in stats['current_logs']:
                print(f"  • {log['name']} ({log['size_mb']} MB)")
        
        # Show some archived files (limit to 5)
        if stats['archived_logs']:
            print(f"\n📦 Recent Archived Files:")
            for log in stats['archived_logs'][:5]:
                print(f"  • {log['name']} ({log['size_mb']} MB)")
            
            if len(stats['archived_logs']) > 5:
                print(f"  ... and {len(stats['archived_logs']) - 5} more")
        
        # Perform log rotation
        print(f"\n🔄 Running Log Rotation...")
        rotation_results = await log_manager.rotate_logs()
        
        if "error" in rotation_results:
            print(f"❌ Rotation error: {rotation_results['error']}")
            return
        
        # Show rotation results
        if rotation_results['rotated_files']:
            print(f"✅ Rotated {len(rotation_results['rotated_files'])} files")
            for file in rotation_results['rotated_files']:
                print(f"  • {Path(file).name}")
        
        if rotation_results['compressed_files']:
            print(f"🗜️  Compressed {len(rotation_results['compressed_files'])} files")
            for file in rotation_results['compressed_files']:
                print(f"  • {Path(file).name}")
        
        if rotation_results['total_space_freed_mb'] > 0:
            print(f"💾 Space freed: {rotation_results['total_space_freed_mb']:.2f} MB")
        
        if not any([rotation_results['rotated_files'], 
                   rotation_results['compressed_files'],
                   rotation_results['total_space_freed_mb'] > 0]):
            print("✅ No log maintenance needed")
        
    except ImportError:
        print("❌ Log manager module not available")
    except Exception as e:
        print(f"❌ Log management failed: {e}")


async def monitor_command():
    """Real-time system monitoring with alerts."""
    print("📊 Alisa System Monitor")
    print("=" * 30)
    
    try:
        from alisa.services.system_monitor import get_system_monitor
        
        monitor = get_system_monitor()
        
        # Take a snapshot first
        print("\n📸 Taking system snapshot...")
        snapshot = await monitor.take_snapshot()
        
        # Show current status
        print(f"\n🖥️  Current System Status:")
        print(f"  CPU Usage: {snapshot.cpu_percent:.1f}%")
        print(f"  Memory Usage: {snapshot.memory_percent:.1f}% ({snapshot.memory_used_mb:.0f}/{snapshot.memory_total_mb:.0f} MB)")
        print(f"  Disk Usage: {snapshot.disk_percent:.1f}% ({snapshot.disk_free_gb:.1f} GB free)")
        print(f"  Load Average: {snapshot.load_avg_1m:.2f}")
        print(f"  Uptime: {snapshot.uptime_hours:.1f} hours")
        
        if snapshot.temperature_c > 0:
            print(f"  Temperature: {snapshot.temperature_c:.1f}°C")
        
        print(f"\n🧠 LLM Status:")
        print(f"  Active Providers: {snapshot.active_llm_providers}")
        print(f"  Total Requests: {snapshot.llm_requests_total}")
        
        # Show recent alerts
        recent_alerts = monitor.get_alerts(minutes=60)
        if recent_alerts:
            print(f"\n⚠️  Recent Alerts (last hour):")
            for alert in recent_alerts[-5:]:  # Show last 5
                timestamp = time.strftime("%H:%M:%S", time.localtime(alert.timestamp))
                level_icon = "🔴" if alert.level == "CRITICAL" else "🟡"
                print(f"  {level_icon} {timestamp} [{alert.level}] {alert.component}: {alert.message}")
        else:
            print(f"\n✅ No recent alerts")
        
        # Show performance summary if we have history
        if len(monitor.snapshots) >= 2:
            summary = monitor.get_performance_summary()
            print(f"\n📈 Performance Summary (last {summary['samples']} samples):")
            print(f"  Avg CPU: {summary['avg_cpu']:.1f}% (Max: {summary['max_cpu']:.1f}%)")
            print(f"  Avg Memory: {summary['avg_memory']:.1f}% (Max: {summary['max_memory']:.1f}%)")
            if summary['avg_temperature'] > 0:
                print(f"  Avg Temperature: {summary['avg_temperature']:.1f}°C (Max: {summary['max_temperature']:.1f}°C)")
        
        # Show alert thresholds
        print(f"\n⚙️  Alert Thresholds:")
        thresholds = monitor.thresholds
        print(f"  CPU: Warning {thresholds['cpu_warning']:.0f}%, Critical {thresholds['cpu_critical']:.0f}%")
        print(f"  Memory: Warning {thresholds['memory_warning']:.0f}%, Critical {thresholds['memory_critical']:.0f}%")
        print(f"  Disk: Warning {thresholds['disk_warning']:.0f}%, Critical {thresholds['disk_critical']:.0f}%")
        print(f"  Temperature: Warning {thresholds['temperature_warning']:.0f}°C, Critical {thresholds['temperature_critical']:.0f}°C")
        
        print(f"\n💡 Use 'python main.py --mode monitor' for continuous monitoring")
        
    except ImportError:
        print("❌ System monitor module not available")
    except Exception as e:
        print(f"❌ System monitoring failed: {e}")
        import traceback
        traceback.print_exc()


async def optimize_command():
    """Analyze and optimize system performance."""
    print("⚡ Alisa System Optimizer")
    print("=" * 40)
    
    try:
        from alisa.services.optimizer import get_optimizer
        
        optimizer = get_optimizer()
        
        # First, analyze the system
        print("\n🔍 Analyzing system performance...")
        analysis = await optimizer.analyze_system()
        
        # Show analysis results
        print("\n📊 System Analysis Results:")
        
        # Memory analysis
        memory = analysis.get("memory", {})
        if "error" not in memory:
            print(f"\n💾 Memory:")
            print(f"  Total: {memory.get('total_mb', 0)} MB")
            print(f"  Available: {memory.get('available_mb', 0)} MB")
            print(f"  Usage: {memory.get('usage_percent', 0):.1f}%")
            print(f"  Cache: {memory.get('cache_percent', 0):.1f}%")
            print(f"  Fragmentation: {memory.get('fragmentation', 'unknown')}")
        
        # Swap analysis
        swap = analysis.get("swap", {})
        if "error" not in swap:
            print(f"\n🔄 Swap:")
            print(f"  Total: {swap.get('total_mb', 0)} MB")
            print(f"  Used: {swap.get('used_mb', 0)} MB")
            print(f"  Usage: {swap.get('usage_percent', 0):.1f}%")
            print(f"  Swappiness: {swap.get('swappiness', 'unknown')}")
        
        # CPU analysis
        cpu = analysis.get("cpu", {})
        if "error" not in cpu:
            print(f"\n🖥️  CPU:")
            print(f"  Cores: {cpu.get('cpu_count', 'unknown')}")
            print(f"  Governor: {cpu.get('governor', 'unknown')}")
            if "available_governors" in cpu:
                print(f"  Available Governors: {', '.join(cpu['available_governors'])}")
            if "current_freq_khz" in cpu:
                print(f"  Current Frequency: {cpu['current_freq_khz'] // 1000} MHz")
        
        # Disk analysis
        disk = analysis.get("disk", {})
        if "error" not in disk:
            print(f"\n💽 Disk:")
            print(f"  Total: {disk.get('total_gb', 0)} GB")
            print(f"  Used: {disk.get('used_gb', 0)} GB")
            print(f"  Free: {disk.get('free_gb', 0)} GB")
            print(f"  Usage: {disk.get('usage_percent', 0):.1f}%")
            print(f"  Storage Type: {disk.get('storage_type', 'unknown')}")
        
        # Network analysis
        network = analysis.get("network", {})
        if "error" not in network:
            print(f"\n🌐 Network:")
            interfaces = network.get("interfaces", [])
            print(f"  Interfaces: {', '.join(interfaces) if interfaces else 'none'}")
            wifi_pm = network.get("wifi_power_management", {})
            if wifi_pm:
                print(f"  WiFi Power Management:")
                for iface, status in wifi_pm.items():
                    print(f"    {iface}: {status}")
        
        # Show recommendations
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            print(f"\n💡 Optimization Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        else:
            print(f"\n✅ No optimization recommendations - system looks good!")
        
        # Ask if user wants to apply optimizations
        if recommendations:
            print(f"\n🔧 Apply Optimizations?")
            print("Available categories: memory, swap, cpu, disk, network")
            print("Enter categories to optimize (comma-separated) or 'all' for everything:")
            print("Press Enter to skip optimization.")
            
            # For CLI, we'll just show what would be applied
            print("\n⚠️  Note: This is a preview. Run with --apply flag to actually apply optimizations.")
            print("Example optimizations that would be applied:")
            print("  • Clear system caches")
            print("  • Optimize swappiness settings")
            print("  • Set CPU governor to ondemand")
            print("  • Disable WiFi power management")
        
    except ImportError:
        print("❌ System optimizer module not available")
    except Exception as e:
        print(f"❌ System optimization failed: {e}")
        import traceback
        traceback.print_exc()


def diagnose_command():
    """Run comprehensive system diagnostics."""
    print("🔍 Alisa System Diagnostics")
    print("=" * 40)
    
    from alisa.core.validator import validate_system, get_system_info
    
    # System info
    print("\n📋 System Information:")
    sys_info = get_system_info()
    print(f"  OS: {sys_info.get('os', 'Unknown')}")
    print(f"  Architecture: {sys_info.get('architecture', 'Unknown')}")
    print(f"  Python: {sys_info.get('python_version', 'Unknown')}")
    print(f"  Total Memory: {sys_info.get('total_memory', 'Unknown')}")
    print(f"  Disk Free: {sys_info.get('disk_free', 'Unknown')}")
    
    # Validation
    print("\n🔧 Component Validation:")
    is_valid, issues = validate_system()
    
    if is_valid:
        print("✅ All components validated successfully")
    else:
        print("❌ Validation issues found:")
        for issue in issues:
            print(f"  • {issue}")
    
    # File permissions
    print("\n📁 File System Check:")
    import os
    from pathlib import Path
    
    project_root = Path(__file__).parent
    config_file = project_root / "config.yaml"
    
    if config_file.exists():
        print(f"✅ Config file exists: {config_file}")
        print(f"  Readable: {os.access(config_file, os.R_OK)}")
        print(f"  Writable: {os.access(config_file, os.W_OK)}")
    else:
        print(f"❌ Config file missing: {config_file}")
    
    # Network connectivity
    print("\n🌐 Network Check:")
    import socket
    
    def check_connection(host, port, timeout=3):
        try:
            socket.create_connection((host, port), timeout)
            return True
        except (socket.timeout, socket.error):
            return False
    
    # Check common services
    services = [
        ("api.openai.com", 443, "OpenAI API"),
        ("generativelanguage.googleapis.com", 443, "Google Gemini"),
        ("api.deepseek.com", 443, "DeepSeek API"),
        ("localhost", 11434, "Ollama (local)")
    ]
    
    for host, port, name in services:
        connected = check_connection(host, port)
        status = "✅" if connected else "❌"
        print(f"  {status} {name}: {host}:{port}")
    
    # Process check
    print("\n🔄 Process Check:")
    try:
        import psutil
        current_process = psutil.Process()
        print(f"  PID: {current_process.pid}")
        print(f"  Memory: {current_process.memory_info().rss / 1024 / 1024:.1f} MB")
        print(f"  CPU: {current_process.cpu_percent():.1f}%")
        print(f"  Threads: {current_process.num_threads()}")
    except ImportError:
        print("  ❌ psutil not available for process monitoring")
    except Exception as e:
        print(f"  ❌ Process check failed: {e}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Alisa AI Assistant CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  alisa_cli.py status      # Show system status
  alisa_cli.py providers   # Show LLM provider status  
  alisa_cli.py config      # Show configuration
  alisa_cli.py test        # Test basic functionality
  alisa_cli.py benchmark   # Run performance benchmark
  alisa_cli.py logs        # Manage log files and rotation
  alisa_cli.py monitor     # Real-time system monitoring
  alisa_cli.py optimize    # Analyze and optimize system performance
  alisa_cli.py diagnose    # Run system diagnostics
  alisa_cli.py memory      # Memory management and cleanup
        """
    )
    
    parser.add_argument(
        "command",
        choices=["status", "providers", "config", "test", "benchmark", "logs", "monitor", "optimize", "diagnose", "memory"],
        help="Command to run"
    )
    
    args = parser.parse_args()
    
    try:
        if args.command == "status":
            status_command()
        elif args.command == "providers":
            asyncio.run(providers_command())
        elif args.command == "config":
            config_command()
        elif args.command == "test":
            asyncio.run(test_command())
        elif args.command == "benchmark":
            asyncio.run(benchmark_command())
        elif args.command == "logs":
            asyncio.run(logs_command())
        elif args.command == "monitor":
            asyncio.run(monitor_command())
        elif args.command == "optimize":
            asyncio.run(optimize_command())
        elif args.command == "diagnose":
            diagnose_command()
        elif args.command == "memory":
            memory_command()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
