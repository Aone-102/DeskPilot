import os
import json
import uuid
import shutil
import pathlib
import datetime
import urllib.parse

USER_DOCUMENTS = pathlib.Path.home() / "Documents"
SHARED_DIR = USER_DOCUMENTS / "DeskPilot" / "공유_파일"
META_FILE = SHARED_DIR / ".meta.json"


def init_shared_dir():
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    if not META_FILE.exists():
        save_meta([])


def load_meta():
    init_shared_dir()
    if not META_FILE.exists():
        return []
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_meta(items):
    try:
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[file_share] save_meta error: {e}")


def list_shared_files():
    """
    Returns list of shared files, synced with actual files on disk.
    """
    init_shared_dir()
    meta_list = load_meta()
    meta_by_name = {item["name"]: item for item in meta_list}

    current_files = []
    updated_meta = []

    for item in SHARED_DIR.iterdir():
        if item.is_dir() or item.name == ".meta.json":
            continue

        file_stat = item.stat()
        file_name = item.name

        meta = meta_by_name.get(file_name)
        if not meta:
            meta = {
                "id": str(uuid.uuid4()),
                "name": file_name,
                "size": file_stat.st_size,
                "uploader": "PC",
                "timestamp": datetime.datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            }

        # Ensure correct size and extension
        meta["size"] = file_stat.st_size
        meta["ext"] = item.suffix.lower()
        current_files.append(meta)
        updated_meta.append(meta)

    # Sort newest first
    current_files.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    save_meta(updated_meta)
    return current_files


def save_uploaded_file(raw_name, content_bytes_or_stream, uploader="스마트폰"):
    """
    Saves an uploaded file to the shared directory with collision protection.
    """
    init_shared_dir()
    # Decode and sanitize file name
    try:
        clean_name = urllib.parse.unquote(raw_name)
    except Exception:
        clean_name = raw_name

    clean_name = os.path.basename(clean_name).strip()
    if not clean_name:
        clean_name = f"upload_{int(datetime.datetime.now().timestamp())}.bin"

    target_path = SHARED_DIR / clean_name
    stem = target_path.stem
    suffix = target_path.suffix
    counter = 1

    while target_path.exists():
        target_path = SHARED_DIR / f"{stem} ({counter}){suffix}"
        counter += 1

    if isinstance(content_bytes_or_stream, bytes):
        with open(target_path, "wb") as f:
            f.write(content_bytes_or_stream)
    else:
        # Stream read
        with open(target_path, "wb") as f:
            shutil.copyfileobj(content_bytes_or_stream, f)

    file_stat = target_path.stat()
    file_info = {
        "id": str(uuid.uuid4()),
        "name": target_path.name,
        "size": file_stat.st_size,
        "uploader": uploader,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ext": target_path.suffix.lower()
    }

    meta_list = load_meta()
    meta_list.insert(0, file_info)
    save_meta(meta_list)

    return file_info


def delete_shared_file(file_id):
    init_shared_dir()
    meta_list = load_meta()
    target = None
    for item in meta_list:
        if item.get("id") == file_id or item.get("name") == file_id:
            target = item
            break

    if target:
        file_path = SHARED_DIR / target["name"]
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                print(f"[file_share] unlink error: {e}")
        meta_list = [m for m in meta_list if m.get("id") != target.get("id")]
        save_meta(meta_list)
        return True
    return False


def get_file_path(file_id_or_name):
    init_shared_dir()
    if not file_id_or_name:
        return None, None
    try:
        clean_target = urllib.parse.unquote(str(file_id_or_name)).strip()
    except Exception:
        clean_target = str(file_id_or_name).strip()

    if not clean_target:
        return None, None

    meta_list = load_meta()
    for item in meta_list:
        if item.get("id") == clean_target or item.get("name") == clean_target:
            p = SHARED_DIR / item["name"]
            if p.exists() and p.is_file():
                return p, item["name"]

    # Direct name fallback
    clean_name = os.path.basename(clean_target)
    if clean_name:
        p = SHARED_DIR / clean_name
        if p.exists() and p.is_file():
            return p, p.name

    return None, None
