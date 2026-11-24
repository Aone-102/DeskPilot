import re
import shutil
import pathlib
import threading
import subprocess

_tunnel_process = None
_tunnel_url = None
_is_starting = False
_lock = threading.Lock()


def find_cloudflared():
    """Finds the cloudflared executable."""
    found = shutil.which("cloudflared")
    if found:
        return found

    candidates = [
        pathlib.Path(r"C:\Program Files\cloudflared\cloudflared.exe"),
        pathlib.Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"),
        pathlib.Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages" / "Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe" / "cloudflared.exe"
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # Search in common winget / local paths
    return None


def get_tunnel_status():
    global _tunnel_process, _tunnel_url, _is_starting
    with _lock:
        cloudflared_bin = find_cloudflared()
        return {
            "available": cloudflared_bin is not None,
            "running": _tunnel_process is not None and _tunnel_process.poll() is None,
            "starting": _is_starting,
            "url": _tunnel_url
        }


def _monitor_tunnel_output(proc):
    global _tunnel_url, _is_starting
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    try:
        for line in proc.stderr:
            line_str = line.decode("utf-8", errors="ignore")
            match = url_pattern.search(line_str)
            if match:
                with _lock:
                    _tunnel_url = match.group(0)
                    _is_starting = False
                print(f"[Cloudflare Tunnel] Public HTTPS URL: {_tunnel_url}")
                break
    except Exception as e:
        print(f"[Cloudflare Tunnel] Monitor error: {e}")
        with _lock:
            _is_starting = False


def start_tunnel(port=48290):
    global _tunnel_process, _tunnel_url, _is_starting
    with _lock:
        if _tunnel_process and _tunnel_process.poll() is None and _tunnel_url:
            return _tunnel_url

        cloudflared_bin = find_cloudflared()
        if not cloudflared_bin:
            return None

        _is_starting = True
        _tunnel_url = None

        cmd = [
            cloudflared_bin,
            "tunnel",
            "--url", f"http://127.0.0.1:{port}"
        ]

        try:
            _tunnel_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
        except Exception as e:
            print(f"[Cloudflare Tunnel] Start error: {e}")
            _is_starting = False
            return None

    # Spawn thread to capture URL
    t = threading.Thread(target=_monitor_tunnel_output, args=(_tunnel_process,), daemon=True)
    t.start()
    return None


def stop_tunnel():
    global _tunnel_process, _tunnel_url, _is_starting
    with _lock:
        if _tunnel_process:
            try:
                _tunnel_process.terminate()
            except Exception:
                pass
            _tunnel_process = None
        _tunnel_url = None
        _is_starting = False
