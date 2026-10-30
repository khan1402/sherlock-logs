"""
metrics.py — collects raw system/infrastructure facts.
No web-framework code lives here on purpose.
"""
import platform  # OS name/version info
import socket  # hostname info

import psutil  # third-party library for CPU/memory stats


def get_hostname() -> str:
    """Return this machine's hostname (e.g. "app-server")."""
    return socket.gethostname()


def get_os_info() -> str:
    """Return a human-readable OS description, e.g. "Linux 5.15.0-generic"."""
    # platform.system() = OS name ("Linux"), platform.release() = kernel version
    return f"{platform.system()} {platform.release()}"


def get_cpu_info() -> dict:
    """Return CPU details: how many cores, and how busy it is right now."""
    return {
        "cores_count": psutil.cpu_count(logical=True),  # logical=True counts hyperthreaded cores too
        "usage_percent": psutil.cpu_percent(interval=1),  # CPU usage measured over 1 second
    }


def get_memory_info() -> dict:
    """Return memory details in MB: total, used, and percent used."""
    mem = psutil.virtual_memory()  # values in bytes
    return {
        # bytes -> MB, rounded to 2 decimals for readability
        "total_mb": round(mem.total / (1024 * 1024), 2),
        "used_mb": round(mem.used / (1024 * 1024), 2),
        "percent_used": mem.percent,  # psutil already gives a percentage
    }


def collect_all() -> dict:
    """
    Bundle everything into one dict. This is the only function
    main.py calls; everything above is a helper.
    """
    return {
        "hostname": get_hostname(),
        "os": get_os_info(),
        "cpu": get_cpu_info(),
        "memory": get_memory_info(),
    }
