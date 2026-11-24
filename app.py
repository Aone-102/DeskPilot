import os
import sys
import re
import json
import time
import uuid
import shutil
import pathlib
import datetime
import threading
import subprocess
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Import modular v2 core modules
import task_scorer
import organizer
import auth
import file_share
import tunnel

# 1. Base Directory & AppData Management (PRD A4)
APP_DIR = pathlib.Path(__file__).parent.resolve()
STATIC_DIR = APP_DIR / "static"

# Standard Windows AppData directory for persistent user data
USER_HOME = pathlib.Path.home()
APPDATA_BASE = pathlib.Path(os.environ.get("APPDATA", str(USER_HOME / "AppData" / "Roaming")))
APPDATA_DIR = APPDATA_BASE / "DeskPilot"
DATA_DIR = APPDATA_DIR / "data"
LOGS_DIR = APPDATA_DIR / "logs"
CONFIG_FILE = APPDATA_DIR / "config.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

TASKS_FILE = DATA_DIR / "tasks.json"
NOTES_FILE = DATA_DIR / "notes.json"
HISTORY_FILE = DATA_DIR / "history.json"
CLIPS_FILE = DATA_DIR / "clips.json"

# Key user folders
DESKTOP_DIR = USER_HOME / "Desktop"
DOWNLOADS_DIR = USER_HOME / "Downloads"
DOCUMENTS_DIR = USER_HOME / "Documents"
STARTUP_DIR = APPDATA_BASE / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_LNK = STARTUP_DIR / "DeskPilot.lnk"
DEFAULT_ORG_DIR = DOCUMENTS_DIR / "DeskPilot" / "정리된_파일"

# PRD Section 6 Default Configuration
DEFAULT_CONFIG = {
    "schemaVersion": 2,
    "firstRunDone": False,
    "organizedDir": str(DEFAULT_ORG_DIR),
    "watchFolders": [
        {"name": "바탕화면", "path": str(DESKTOP_DIR), "enabled": True},
        {"name": "다운로드", "path": str(DOWNLOADS_DIR), "enabled": True}
    ],
    "safety": {
        "minAgeSeconds": 60,
        "skipExtensions": [".crdownload", ".part", ".tmp", ".partial", ".download", ".lnk", ".url", ".ini"],
        "ignorePatterns": [],
        "ignorePaths": []
    },
    "automation": {
        "autoStart": False,
        "cleanOnStartup": False,  # PRD B1: 기본값은 반드시 OFF
        "showWindowOnStartup": True,
        "periodic": {"enabled": False, "minutes": 30},
        "pausedUntil": None
    },
    "rules": organizer.DEFAULT_RULES,
    "phone": {
        "enabled": True,
        "port": 48290,
        "devices": []
    },
    "ui": {
        "language": "ko",
        "closeToTray": True
    }
}


# --- Migration from v1 to v2 (PRD 4장, A1 & A4) ---
def migrate_v1_data():
    local_cfg = APP_DIR / "config.json"
    local_data = APP_DIR / "data"

    if local_cfg.exists() and not CONFIG_FILE.exists():
        try:
            # Backup v1 config
            bak_cfg = APP_DIR / "config.json.v1.bak"
            shutil.copy2(local_cfg, bak_cfg)
            with open(local_cfg, "r", encoding="utf-8") as f:
                old = json.load(f)
            # Create v2 config merging old values
            merged = DEFAULT_CONFIG.copy()
            if "organized_dir" in old:
                merged["organizedDir"] = old["organized_dir"]
            if "watch_folders" in old:
                merged["watchFolders"] = old["watch_folders"]
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Migration] config error: {e}")

    # Migrate data files
    if local_data.exists():
        for filename in ["tasks.json", "notes.json", "history.json"]:
            src_f = local_data / filename
            dest_f = DATA_DIR / filename
            if src_f.exists() and not dest_f.exists():
                try:
                    shutil.copy2(src_f, APP_DIR / f"{filename}.v1.bak")
                    shutil.copy2(src_f, dest_f)
                except Exception as e:
                    print(f"[Migration] {filename} error: {e}")

    # Check and repair corrupted UTF-8 tasks (A1)
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                tasks_data = json.load(f)
            # Check if any task text contains corrupted question marks
            needs_repair = any("???" in str(t.get("text") or t.get("title", "")) for t in tasks_data)
            if needs_repair or not tasks_data:
                sample_tasks = [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "DeskPilot v2 둘러보기",
                        "priority": "urgent",
                        "dueDate": datetime.date.today().isoformat(),
                        "estimateMin": 15,
                        "tags": ["가이드"],
                        "done": False,
                        "date": datetime.date.today().isoformat(),
                        "carriedCount": 0,
                        "createdAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "스마트폰 QR 코드로 연동하기",
                        "priority": "high",
                        "dueDate": datetime.date.today().isoformat(),
                        "estimateMin": 10,
                        "tags": ["연동"],
                        "done": False,
                        "date": datetime.date.today().isoformat(),
                        "carriedCount": 0,
                        "createdAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "바탕화면 / 다운로드 폴더 안전 정리 테스트",
                        "priority": "normal",
                        "dueDate": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
                        "estimateMin": 30,
                        "tags": ["정리"],
                        "done": False,
                        "date": datetime.date.today().isoformat(),
                        "carriedCount": 0,
                        "createdAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                ]
                save_json(TASKS_FILE, sample_tasks)
    except Exception as e:
        print(f"[Migration] task repair error: {e}")

    # Check and repair notes (A1)
    try:
        if NOTES_FILE.exists():
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                notes_data = json.load(f)
            if "???" in str(notes_data.get("content", "")) or not notes_data.get("content"):
                sample_note = {
                    "content": "✨ DeskPilot v2 실행 완료!\n스마트폰과 연동하면 침대나 외출 중에도 할 일과 메모를 언제든 확인하고 체크할 수 있습니다.",
                    "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_json(NOTES_FILE, sample_note)
    except Exception as e:
        print(f"[Migration] note repair error: {e}")


def load_config():
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            # Sync startup link existence
            cfg.setdefault("automation", {})["autoStart"] = STARTUP_LNK.exists()
            return cfg
    except Exception as e:
        print(f"[Error] load_config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] save_config: {e}")


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] save_json {path}: {e}")


# --- Windows Startup Registration (PRD A6) ---
def set_auto_startup(enable: bool):
    try:
        STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        if enable:
            target_exe = sys.executable
            # If running via pythonw or python
            if "python.exe" in target_exe.lower():
                pyw = pathlib.Path(target_exe).parent / "pythonw.exe"
                if pyw.exists():
                    target_exe = str(pyw)

            app_script = str(APP_DIR / "app.py")
            # PowerShell shortcut creation
            ps_cmd = f"""
            $WshShell = New-Object -comObject WScript.Shell
            $Shortcut = $WshShell.CreateShortcut('{STARTUP_LNK}')
            $Shortcut.TargetPath = '{target_exe}'
            $Shortcut.Arguments = '"{app_script}" --startup'
            $Shortcut.WorkingDirectory = '{APP_DIR}'
            $Shortcut.Description = 'DeskPilot v2 Auto Launcher'
            $Shortcut.IconLocation = 'imageres.dll,110'
            $Shortcut.Save()
            """
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True, capture_output=True)
            return True, "부팅 시 자동 실행이 활성화되었습니다."
        else:
            if STARTUP_LNK.exists():
                STARTUP_LNK.unlink()
            return True, "부팅 시 자동 실행이 해제되었습니다."
    except Exception as e:
        return False, str(e)


# --- Periodic Background Scheduler ---
def background_scheduler():
    while True:
        try:
            cfg = load_config()
            auto_cfg = cfg.get("automation", {})
            periodic = auto_cfg.get("periodic", {})
            if periodic.get("enabled", False):
                interval = max(5, periodic.get("minutes", 30))
                time.sleep(interval * 60)
                # Run organize
                scan_res = organizer.scan_candidates(cfg)
                if scan_res["files"]:
                    batch = organizer.execute_organize_batch(scan_res["files"], cfg.get("organizedDir"), trigger="periodic")
                    if batch["count"] > 0:
                        history = load_json(HISTORY_FILE, [])
                        history.insert(0, batch)
                        save_json(HISTORY_FILE, history[:30])
            else:
                time.sleep(60)
        except Exception as e:
            print(f"[Scheduler Error] {e}")
            time.sleep(60)


# --- Multi-threaded HTTP Request Handler ---
class DeskPilotV2Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Clean logging
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-DeskPilot-Device-Token")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-DeskPilot-Device-Token")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def is_local_request(self):
        client_ip = self.client_address[0]
        return client_ip in ("127.0.0.1", "::1", "localhost")

    def check_phone_auth(self, config):
        """Checks smartphone device token authentication."""
        if self.is_local_request():
            return True, {"name": "Local Desktop"}

        # Token from header
        token = self.headers.get("X-DeskPilot-Device-Token")
        if not token:
            auth_hdr = self.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                token = auth_hdr.split(" ", 1)[1].strip()

        ok, dev = auth.verify_phone_token(config, token)
        return ok, dev

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        cfg = load_config()

        # 1. Phone QR Code image endpoint
        if path == "/api/phone/qr.svg":
            lan_ip = auth.get_local_lan_ip()
            port = cfg.get("phone", {}).get("port", 48290)
            code, secret = auth.get_or_create_active_pairing()

            t_status = tunnel.get_tunnel_status()
            if t_status.get("running") and t_status.get("url"):
                pairing_url = f"{t_status['url']}/?pair={code}"
            else:
                pairing_url = f"http://{lan_ip}:{port}/?pair={code}"

            svg_data = auth.generate_qr_svg(pairing_url).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(svg_data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(svg_data)
            return

        # 2. System Status API
        if path == "/api/status":
            tasks = load_json(TASKS_FILE, [])
            today_str = datetime.date.today().isoformat()

            # Auto carryover (A2)
            tasks, carried = task_scorer.auto_carryover_tasks(tasks, today_str)
            if carried > 0:
                save_json(TASKS_FILE, tasks)

            today_tasks = [t for t in tasks if t.get("date") == today_str]
            done_count = sum(1 for t in today_tasks if t.get("done"))

            scan = organizer.scan_candidates(cfg)
            lan_ip = auth.get_local_lan_ip()
            hostname = auth.get_pc_hostname()
            code, _ = auth.get_or_create_active_pairing()

            self.send_json({
                "app": "DeskPilot",
                "version": "2.0.0",
                "hostname": hostname,
                "lan_ip": lan_ip,
                "today": today_str,
                "startup_enabled": STARTUP_LNK.exists(),
                "first_run_done": cfg.get("firstRunDone", False),
                "tasks_summary": {
                    "total": len(today_tasks),
                    "done": done_count,
                    "remaining": len(today_tasks) - done_count,
                    "carried": sum(t.get("carriedCount", 0) for t in today_tasks)
                },
                "pending_files": scan["total_count"],
                "pending_size": scan["total_size"],
                "phone_connected_count": len(cfg.get("phone", {}).get("devices", [])),
                "active_pairing_code": code
            })
            return

        # 3. Tasks API
        elif path == "/api/tasks":
            tasks = load_json(TASKS_FILE, [])
            today_str = datetime.date.today().isoformat()
            tasks, carried = task_scorer.auto_carryover_tasks(tasks, today_str)
            if carried > 0:
                save_json(TASKS_FILE, tasks)
            sorted_tasks = task_scorer.sort_tasks(tasks, datetime.date.today())
            self.send_json({"tasks": sorted_tasks, "carried_count": carried})
            return

        # 4. Notes API
        elif path == "/api/notes":
            notes = load_json(NOTES_FILE, {"content": "", "updated_at": ""})
            self.send_json(notes)
            return

        # 5. File Organize Scan
        elif path == "/api/organize/scan":
            self.send_json(organizer.scan_candidates(cfg))
            return

        # 6. Organize History
        elif path == "/api/organize/history":
            history = load_json(HISTORY_FILE, [])
            self.send_json({"history": history})
            return

        # 7. Rules API
        elif path == "/api/rules":
            rules = cfg.get("rules", organizer.DEFAULT_RULES)
            self.send_json({"rules": rules})
            return

        # 8. Settings API
        elif path == "/api/settings":
            self.send_json(cfg)
            return

        # 9. Phone Info API
        elif path == "/api/phone/info":
            lan_ip = auth.get_local_lan_ip()
            port = cfg.get("phone", {}).get("port", 48290)
            code, _ = auth.get_or_create_active_pairing()
            devices = cfg.get("phone", {}).get("devices", [])
            t_status = tunnel.get_tunnel_status()

            if t_status.get("running") and t_status.get("url"):
                pairing_url = f"{t_status['url']}/?pair={code}"
            else:
                pairing_url = f"http://{lan_ip}:{port}/?pair={code}"

            self.send_json({
                "hostname": auth.get_pc_hostname(),
                "lan_ip": lan_ip,
                "port": port,
                "pairing_code": code,
                "pairing_url": pairing_url,
                "tunnel": t_status,
                "devices": devices
            })
            return

        # 9-1. Tunnel Status API
        elif path == "/api/tunnel/status":
            self.send_json(tunnel.get_tunnel_status())
            return

        # 10. Shared Files List API
        elif path == "/api/shared/files":
            files = file_share.list_shared_files()
            self.send_json({"files": files})
            return

        # 10-1. Shared Clips (Text / Link) List API
        elif path == "/api/shared/clips":
            clips = load_json(CLIPS_FILE, [])
            self.send_json({"clips": clips})
            return

        # 11. Shared File Download API
        elif path.startswith("/api/shared/download"):
            file_id = query.get("id", [""])[0] or query.get("name", [""])[0]
            if not file_id:
                subpath = path[len("/api/shared/download"):].strip("/")
                if subpath:
                    file_id = urllib.parse.unquote(subpath)

            file_path, original_name = file_share.get_file_path(file_id)
            if file_path and file_path.exists() and file_path.is_file():
                file_size = file_path.stat().st_size
                encoded_name = urllib.parse.quote(original_name)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{encoded_name}"; filename*=UTF-8\'\'{encoded_name}')
                self.send_header("Content-Length", str(file_size))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(file_path, "rb") as f_in:
                    shutil.copyfileobj(f_in, self.wfile)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        # 12. Static files serving
        file_to_serve = STATIC_DIR / "index.html"
        if path != "/" and path != "" and path != "/m":
            target = STATIC_DIR / path.lstrip("/")
            if target.exists() and not target.is_dir():
                file_to_serve = target

        if file_to_serve.exists():
            content_type = "text/html; charset=utf-8"
            suffix = file_to_serve.suffix.lower()
            if suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif suffix == ".svg":
                content_type = "image/svg+xml; charset=utf-8"
            elif suffix == ".png":
                content_type = "image/png"
            elif suffix == ".ico":
                content_type = "image/x-icon"

            with open(file_to_serve, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            try:
                return json.loads(raw.decode("cp949"))
            except Exception:
                return {}

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        cfg = load_config()

        # 0. Shared File Upload API (Direct binary stream)
        if path == "/api/shared/upload":
            if not self.is_local_request():
                auth_ok, dev = self.check_phone_auth(cfg)
                if not auth_ok:
                    self.send_json({"success": False, "message": "스마트폰 인증이 필요합니다."}, 401)
                    return
                uploader = dev.get("name", "스마트폰") if dev else "스마트폰"
            else:
                uploader = "PC"

            length = int(self.headers.get("Content-Length", 0))
            raw_filename = self.headers.get("X-File-Name", f"upload_{int(time.time())}.bin")
            file_bytes = self.rfile.read(length) if length > 0 else b""
            file_info = file_share.save_uploaded_file(raw_filename, file_bytes, uploader)
            self.send_json({"success": True, "file": file_info})
            return

        body = self.read_json_body()

        # 1. Smartphone Confirmation Endpoint (No prior token required)
        if path == "/api/phone/confirm":
            code = body.get("code")
            device_name = body.get("device_name", "스마트폰")
            valid, _ = auth.verify_pairing_code(code)
            if valid:
                raw_token, dev_info = auth.register_new_device(cfg, device_name)
                save_config(cfg)
                self.send_json({
                    "success": True,
                    "token": raw_token,
                    "device": dev_info,
                    "hostname": auth.get_pc_hostname()
                })
            else:
                self.send_json({
                    "success": False,
                    "message": "페어링 코드가 만료되었거나 올바르지 않습니다."
                }, 400)
            return

        # 2. Check Auth for phone requests
        if not self.is_local_request():
            auth_ok, dev = self.check_phone_auth(cfg)
            if not auth_ok:
                self.send_json({"success": False, "message": "스마트폰 인증이 필요합니다. QR 코드를 스캔하세요."}, 401)
                return

            # Phone security: cannot organize or change system settings
            if path in ("/api/organize/run", "/api/organize/undo", "/api/settings/startup"):
                self.send_json({"success": False, "message": "보안 정책상 스마트폰에서는 이 작업을 실행할 수 없습니다."}, 403)
                return

        # 3. Add Task
        if path == "/api/tasks":
            tasks = load_json(TASKS_FILE, [])
            title = body.get("title") or body.get("text", "")
            title = title.strip()
            if not title:
                self.send_json({"success": False, "message": "할 일 제목을 입력해주세요."}, 400)
                return

            new_task = {
                "id": str(uuid.uuid4()),
                "title": title,
                "text": title,
                "priority": body.get("priority", "normal"),
                "dueDate": body.get("dueDate", datetime.date.today().isoformat()),
                "estimateMin": int(body.get("estimateMin", 30)),
                "tags": body.get("tags", []),
                "done": False,
                "doneAt": None,
                "date": datetime.date.today().isoformat(),
                "carriedCount": 0,
                "createdAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            tasks.insert(0, new_task)
            save_json(TASKS_FILE, tasks)
            self.send_json({"success": True, "task": new_task})
            return

        # 3-1. Batch Add Tasks (e.g. from Memo or multiline text)
        elif path == "/api/tasks/batch":
            titles = body.get("titles", [])
            priority = body.get("priority", "normal")
            due_date = body.get("dueDate", datetime.date.today().isoformat())
            estimate_min = int(body.get("estimateMin", 30))
            tags = body.get("tags", ["메모"])

            tasks = load_json(TASKS_FILE, [])
            added_tasks = []
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for item in titles:
                t_title = str(item).strip()
                if not t_title:
                    continue
                # Strip leading checklist / bullet markdown (e.g., "- [ ] ", "- ", "* ", "1. ")
                clean_title = re.sub(r"^(\s*[-*•]|\d+\.)(\s*\[[\sXx]?\])?\s*", "", t_title).strip()
                if not clean_title:
                    clean_title = t_title

                new_t = {
                    "id": str(uuid.uuid4()),
                    "title": clean_title,
                    "text": clean_title,
                    "priority": priority,
                    "dueDate": due_date,
                    "estimateMin": estimate_min,
                    "tags": tags,
                    "done": False,
                    "doneAt": None,
                    "date": datetime.date.today().isoformat(),
                    "carriedCount": 0,
                    "createdAt": now_str,
                    "updatedAt": now_str
                }
                tasks.insert(0, new_t)
                added_tasks.append(new_t)

            if added_tasks:
                save_json(TASKS_FILE, tasks)

            self.send_json({"success": True, "count": len(added_tasks), "tasks": added_tasks})
            return

        # 4. Manual Carryover
        elif path == "/api/tasks/carryover":
            tasks = load_json(TASKS_FILE, [])
            today_str = datetime.date.today().isoformat()
            tasks, carried = task_scorer.auto_carryover_tasks(tasks, today_str)
            save_json(TASKS_FILE, tasks)
            self.send_json({"success": True, "carried_count": carried})
            return

        # 5. Notes Save
        elif path == "/api/notes":
            content = body.get("content", "")
            data = {
                "content": content,
                "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_json(NOTES_FILE, data)
            self.send_json({"success": True})
            return

        # 6. Execute Organize Batch
        elif path == "/api/organize/run":
            selected_files = body.get("files")
            if selected_files is None:
                scan_res = organizer.scan_candidates(cfg)
                selected_files = scan_res["files"]

            org_dir = cfg.get("organizedDir", str(DEFAULT_ORG_DIR))
            batch = organizer.execute_organize_batch(selected_files, org_dir, trigger="manual")

            if batch["count"] > 0 or batch["errors"]:
                history = load_json(HISTORY_FILE, [])
                history.insert(0, batch)
                save_json(HISTORY_FILE, history[:30])

            self.send_json({
                "success": True,
                "moved_count": batch["count"],
                "errors": batch["errors"],
                "batch_id": batch["batchId"]
            })
            return

        # 7. Undo Organize Batch
        elif path == "/api/organize/undo":
            history = load_json(HISTORY_FILE, [])
            target_batch_id = body.get("batch_id")

            target_batch = None
            if target_batch_id:
                for b in history:
                    if b.get("batchId") == target_batch_id and not b.get("undoneAt"):
                        target_batch = b
                        break
            else:
                for b in history:
                    if not b.get("undoneAt") and b.get("count", 0) > 0:
                        target_batch = b
                        break

            if not target_batch:
                self.send_json({"success": False, "message": "되돌릴 수 있는 정리 내역이 없습니다."})
                return

            res = organizer.undo_batch(target_batch)
            save_json(HISTORY_FILE, history)
            self.send_json(res)
            return

        # 8. Update Rules
        elif path == "/api/rules":
            new_rules = body.get("rules", [])
            cfg["rules"] = new_rules
            save_config(cfg)
            self.send_json({"success": True, "rules": new_rules})
            return

        # 9. Update Settings
        elif path == "/api/settings":
            cfg.update(body)
            save_config(cfg)
            self.send_json({"success": True, "config": cfg})
            return

        # 10. Toggle Windows Auto-Startup
        elif path == "/api/settings/startup":
            enable = body.get("enable", False)
            ok, msg = set_auto_startup(enable)
            cfg = load_config()
            cfg.setdefault("automation", {})["autoStart"] = STARTUP_LNK.exists()
            save_config(cfg)
            self.send_json({"success": ok, "message": msg, "enabled": cfg["automation"]["autoStart"]})
            return

        # 11. Revoke Phone Device
        elif path == "/api/phone/devices/delete":
            device_id = body.get("device_id")
            revoked = auth.revoke_device(cfg, device_id)
            save_config(cfg)
            self.send_json({"success": revoked})
            return

        # 12. Open Folder in Explorer
        elif path == "/api/system/open_folder":
            folder_path = body.get("path", "")
            if folder_path and os.path.exists(folder_path):
                subprocess.Popen(f'explorer "{folder_path}"')
                self.send_json({"success": True})
            else:
                self.send_json({"success": False, "message": "폴더가 존재하지 않습니다."})
            return

        # 13. Open Logs Folder
        elif path == "/api/system/open_logs":
            subprocess.Popen(f'explorer "{LOGS_DIR}"')
            self.send_json({"success": True})
            return

        # 14. Open Shared Folder
        elif path == "/api/shared/open_folder":
            file_share.init_shared_dir()
            subprocess.Popen(f'explorer "{file_share.SHARED_DIR}"')
            self.send_json({"success": True})
            return

        # 15. Toggle Cloudflare Quick Tunnel (External LTE/5G access)
        elif path == "/api/tunnel/toggle":
            enable = body.get("enable", False)
            port = cfg.get("phone", {}).get("port", 48290)
            if enable:
                tunnel.start_tunnel(port)
            else:
                tunnel.stop_tunnel()
            self.send_json({"success": True, "tunnel": tunnel.get_tunnel_status()})
            return

        # 16. Shared Clips API (Send text or link)
        elif path == "/api/shared/clips":
            content = body.get("content", "").strip()
            if not content:
                self.send_json({"success": False, "message": "전송할 내용을 입력해주세요."}, 400)
                return

            uploader = "PC"
            if not self.is_local_request():
                auth_ok, dev = self.check_phone_auth(cfg)
                if dev:
                    uploader = dev.get("name", "스마트폰")
                else:
                    uploader = "스마트폰"
            else:
                custom_uploader = body.get("uploader")
                if custom_uploader:
                    uploader = custom_uploader

            is_url = bool(re.match(r"^https?://[^\s]+", content, re.IGNORECASE))
            clip_type = "url" if is_url else "text"

            new_clip = {
                "id": str(uuid.uuid4()),
                "type": clip_type,
                "content": content,
                "uploader": uploader,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            clips = load_json(CLIPS_FILE, [])
            clips.insert(0, new_clip)
            save_json(CLIPS_FILE, clips[:100])

            self.send_json({"success": True, "clip": new_clip})
            return

        # 17. Delete Shared Clip API
        elif path == "/api/shared/clips/delete":
            clip_id = body.get("clip_id")
            clips = load_json(CLIPS_FILE, [])
            new_clips = [c for c in clips if c.get("id") != clip_id]
            save_json(CLIPS_FILE, new_clips)
            self.send_json({"success": True})
            return

        self.send_response(404)
        self.end_headers()

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()
        cfg = load_config()

        if not self.is_local_request():
            auth_ok, _ = self.check_phone_auth(cfg)
            if not auth_ok:
                self.send_json({"success": False, "message": "스마트폰 인증이 필요합니다."}, 401)
                return

        if path.startswith("/api/tasks/"):
            task_id = path.replace("/api/tasks/", "").strip()
            tasks = load_json(TASKS_FILE, [])
            found = False
            for t in tasks:
                if t.get("id") == task_id:
                    for k in ["done", "title", "text", "priority", "dueDate", "estimateMin", "tags", "date"]:
                        if k in body:
                            t[k] = body[k]
                    t["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if body.get("done") and not t.get("doneAt"):
                        t["doneAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    elif not body.get("done"):
                        t["doneAt"] = None
                    found = True
                    break
            if found:
                save_json(TASKS_FILE, tasks)
                self.send_json({"success": True})
            else:
                self.send_json({"success": False, "message": "Task not found"}, 404)
            return

        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        cfg = load_config()

        if not self.is_local_request():
            auth_ok, _ = self.check_phone_auth(cfg)
            if not auth_ok:
                self.send_json({"success": False, "message": "스마트폰 인증이 필요합니다."}, 401)
                return

        if path.startswith("/api/tasks/"):
            task_id = path.replace("/api/tasks/", "").strip()
            tasks = load_json(TASKS_FILE, [])
            new_tasks = [t for t in tasks if t.get("id") != task_id]
            save_json(TASKS_FILE, new_tasks)
            self.send_json({"success": True})
            return

        elif path.startswith("/api/shared/files/"):
            file_id = path.replace("/api/shared/files/", "").strip()
            deleted = file_share.delete_shared_file(file_id)
            self.send_json({"success": deleted})
            return

        elif path.startswith("/api/shared/clips/"):
            clip_id = path.replace("/api/shared/clips/", "").strip()
            clips = load_json(CLIPS_FILE, [])
            new_clips = [c for c in clips if c.get("id") != clip_id]
            save_json(CLIPS_FILE, new_clips)
            self.send_json({"success": True})
            return

        self.send_response(404)
        self.end_headers()


def launch_gui_window(port: int):
    url = f"http://127.0.0.1:{port}"
    chrome_path = pathlib.Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    chrome_user_data = APPDATA_DIR / ".chrome_profile"

    if chrome_path.exists():
        cmd = [
            str(chrome_path),
            f"--app={url}",
            f"--user-data-dir={chrome_user_data}",
            "--window-size=1180,820",
            "--window-position=160,80"
        ]
        try:
            subprocess.Popen(cmd)
            return
        except Exception as e:
            print(f"[Error] launching Chrome app: {e}")

    import webbrowser
    webbrowser.open(url)


def check_existing_instance(port=48290):
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("app") == "DeskPilot":
                return True
    except Exception:
        pass
    return False


def main():
    migrate_v1_data()

    is_startup = "--startup" in sys.argv
    is_silent = "--silent" in sys.argv

    # Single instance check (PRD C8)
    if check_existing_instance(48290):
        print("[DeskPilot] Already running on port 48290.")
        if is_startup:
            config = load_config()
            if config.get("automation", {}).get("cleanOnStartup", False):
                try:
                    import urllib.request
                    req = urllib.request.Request("http://127.0.0.1:48290/api/organize/run", data=b"{}", headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=2.0)
                except Exception:
                    pass
        if not is_silent:
            launch_gui_window(48290)
        sys.exit(0)

    config = load_config()

    # Startup Action (PRD B1: check cleanOnStartup)
    if is_startup:
        if config.get("automation", {}).get("cleanOnStartup", False):
            print("[DeskPilot] Executing startup auto file organize...")
            scan_res = organizer.scan_candidates(config)
            if scan_res["files"]:
                batch = organizer.execute_organize_batch(scan_res["files"], config.get("organizedDir"), trigger="startup")
                if batch["count"] > 0:
                    history = load_json(HISTORY_FILE, [])
                    history.insert(0, batch)
                    save_json(HISTORY_FILE, history[:30])

        if not config.get("automation", {}).get("showWindowOnStartup", True) or is_silent:
            print("[DeskPilot] Startup silent mode complete.")
            if config.get("automation", {}).get("periodic", {}).get("enabled", False):
                background_scheduler()
            return

    # Start Background scheduler thread
    t = threading.Thread(target=background_scheduler, daemon=True)
    t.start()

    # Create Desktop shortcut if not exists
    desktop_lnk = DESKTOP_DIR / "DeskPilot.lnk"
    if not desktop_lnk.exists():
        vbs_runner = APP_DIR / "run.vbs"
        ps_cmd = f"""
        $WshShell = New-Object -comObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut('{desktop_lnk}')
        $Shortcut.TargetPath = 'wscript.exe'
        $Shortcut.Arguments = '"{vbs_runner}"'
        $Shortcut.WorkingDirectory = '{APP_DIR}'
        $Shortcut.Description = 'DeskPilot v2 - 스마트 데스크탑 비서'
        $Shortcut.IconLocation = 'imageres.dll,110'
        $Shortcut.Save()
        """
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True, capture_output=True)
        except Exception:
            pass

    # Start Multi-threaded HTTP server binding 0.0.0.0
    port = config.get("phone", {}).get("port", 48290)
    server = None
    for p in range(port, port + 10):
        try:
            # Bind 0.0.0.0 so phone on LAN can reach the server
            server = ThreadingHTTPServer(("0.0.0.0", p), DeskPilotV2Handler)
            port = p
            break
        except OSError:
            continue

    if not server:
        print("[Error] Could not bind to port in range 48290-48300")
        return

    lan_ip = auth.get_local_lan_ip()
    print(f"==================================================")
    print(f"  DeskPilot v2 Server Started!")
    print(f"  - Local PC UI:  http://127.0.0.1:{port}")
    print(f"  - Phone LAN UI: http://{lan_ip}:{port}")
    print(f"==================================================")

    # Launch GUI window in separate thread
    threading.Thread(target=lambda: (time.sleep(0.4), launch_gui_window(port)), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[DeskPilot] Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
