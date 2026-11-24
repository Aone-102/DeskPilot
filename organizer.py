import os
import time
import uuid
import shutil
import pathlib
import datetime

# Excluded by default
SYSTEM_EXCLUDED_EXTS = {
    ".lnk", ".url", ".ini", ".sys", ".dll",
    ".crdownload", ".part", ".tmp", ".partial", ".download"
}
SYSTEM_EXCLUDED_FILES = {
    "desktop.ini", "thumbs.db", "deskpilot.lnk", "icon.ico"
}

DEFAULT_RULES = [
    {
        "id": "docs",
        "name": "문서",
        "enabled": True,
        "match": {
            "extensions": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".hwp", ".hwpx", ".csv"],
            "keywords": []
        },
        "destination": "문서"
    },
    {
        "id": "images",
        "name": "이미지",
        "enabled": True,
        "match": {
            "extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"],
            "keywords": []
        },
        "destination": "이미지"
    },
    {
        "id": "archives",
        "name": "압축파일",
        "enabled": True,
        "match": {
            "extensions": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "keywords": []
        },
        "destination": "압축파일"
    },
    {
        "id": "installers",
        "name": "설치파일",
        "enabled": True,
        "match": {
            "extensions": [".exe", ".msi", ".iso"],
            "keywords": []
        },
        "destination": "설치파일"
    },
    {
        "id": "media",
        "name": "미디어",
        "enabled": True,
        "match": {
            "extensions": [".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac"],
            "keywords": []
        },
        "destination": "미디어"
    },
    {
        "id": "code",
        "name": "코드",
        "enabled": False,  # PRD B3: 코드 카테고리는 기본 OFF로 하여 소스코드 유실 방지
        "match": {
            "extensions": [".py", ".js", ".ts", ".html", ".css", ".json", ".sql", ".java", ".c", ".cpp"],
            "keywords": []
        },
        "destination": "코드"
    }
]


def match_rule_for_file(filename, rules):
    name_lower = filename.lower()
    suffix_lower = pathlib.Path(filename).suffix.lower()

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        match_cfg = rule.get("match", {})
        exts = [e.lower() for e in match_cfg.get("extensions", [])]
        keywords = [k.lower() for k in match_cfg.get("keywords", []) if k.strip()]

        # Extension match
        if suffix_lower and suffix_lower in exts:
            return rule

        # Keyword match in filename
        for kw in keywords:
            if kw in name_lower:
                return rule

    return None


def scan_candidates(config, safety_cfg=None):
    """
    PRD 5.2 파이프라인:
    수집 -> 제외(숨김, 시스템, 바로가기, 출력폴더, 사용자 제외, 너무 최근 수정, 다운로드 중) -> 규칙 평가
    """
    if safety_cfg is None:
        safety_cfg = config.get("safety", {})

    min_age_seconds = safety_cfg.get("minAgeSeconds", 60)
    user_skip_exts = set(e.lower() for e in safety_cfg.get("skipExtensions", []))
    ignore_paths = set(p.lower() for p in safety_cfg.get("ignorePaths", []))
    ignore_patterns = [p.lower() for p in safety_cfg.get("ignorePatterns", [])]

    rules = config.get("rules", DEFAULT_RULES)
    watch_folders = config.get("watchFolders", config.get("watch_folders", []))
    org_dir = pathlib.Path(config.get("organizedDir", config.get("organized_dir", ""))).resolve()

    now = time.time()
    candidates = []
    total_size = 0

    for wf in watch_folders:
        if not wf.get("enabled", True):
            continue
        folder_path = pathlib.Path(wf.get("path", "")).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            continue

        try:
            for item in folder_path.iterdir():
                # 1. PRD B3: 폴더는 절대 이동하지 않음
                if item.is_dir():
                    continue

                item_resolved = item.resolve()
                name = item.name
                name_lower = name.lower()
                suffix_lower = item.suffix.lower()

                # 2. Skip temporary / hidden / lock files
                if name_lower.startswith("~$") or name_lower.startswith("."):
                    continue

                # 3. Skip system & downloading extensions (.crdownload, .part, .tmp, .lnk, .url)
                if suffix_lower in SYSTEM_EXCLUDED_EXTS or suffix_lower in user_skip_exts:
                    continue
                if name_lower in SYSTEM_EXCLUDED_FILES:
                    continue

                # 4. PRD A3: 정리 저장 폴더 내부의 파일은 절대 감시/정리하지 않음
                try:
                    if org_dir in item_resolved.parents or item_resolved.parent == org_dir:
                        continue
                except Exception:
                    pass

                # 5. User ignore paths / patterns
                if str(item_resolved).lower() in ignore_paths:
                    continue
                if any(pat in name_lower for pat in ignore_patterns if pat):
                    continue

                # 6. PRD B2: 최근 N초(기본 60초) 이내 수정된 파일 건너뜀 (다운로드 중이거나 작성 중)
                try:
                    stat_info = item.stat()
                    if (now - stat_info.st_mtime) < min_age_seconds:
                        continue
                    file_size = stat_info.st_size
                except Exception:
                    continue

                # 7. Check if file is currently open/locked
                try:
                    with open(item, "rb") as f_test:
                        pass
                except (IOError, OSError, PermissionError):
                    continue

                # 8. Evaluate rules
                matched_rule = match_rule_for_file(name, rules)
                category = matched_rule["name"] if matched_rule else "기타"
                dest_subfolder = matched_rule.get("destination", "기타") if matched_rule else "기타"

                # Check if code category is disabled
                if category == "코드" and matched_rule and not matched_rule.get("enabled", False):
                    continue

                candidates.append({
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "path": str(item_resolved),
                    "folder": wf.get("name", folder_path.name),
                    "category": category,
                    "destination": dest_subfolder,
                    "ext": suffix_lower,
                    "size": file_size,
                    "selected": True
                })
                total_size += file_size
        except Exception as e:
            print(f"[Error] scanning folder {folder_path}: {e}")

    return {
        "files": candidates,
        "total_count": len(candidates),
        "total_size": total_size
    }


def execute_organize_batch(candidates, org_dir_path, trigger="manual"):
    """
    Executes movement with collision safety, error recording, and batch history logging.
    """
    org_dir = pathlib.Path(org_dir_path).resolve()
    org_dir.mkdir(parents=True, exist_ok=True)

    batch_id = str(uuid.uuid4())
    started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    items_record = []
    moved_count = 0
    errors = []

    for file_info in candidates:
        if not file_info.get("selected", True):
            continue

        src = pathlib.Path(file_info["path"])
        if not src.exists():
            continue

        dest_subfolder = file_info.get("destination", "기타")
        target_dir = org_dir / dest_subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        dest = target_dir / src.name

        # Resolve name collisions: file (1).ext
        counter = 1
        stem = src.stem
        suffix = src.suffix
        while dest.exists():
            dest = target_dir / f"{stem} ({counter}){suffix}"
            counter += 1

        try:
            shutil.move(str(src), str(dest))
            moved_count += 1
            items_record.append({
                "from": str(src),
                "to": str(dest),
                "name": src.name,
                "rule": file_info.get("category", "기타"),
                "size": file_info.get("size", 0),
                "status": "ok",
                "error": None
            })
        except Exception as e:
            err_msg = str(e)
            errors.append({"file": src.name, "error": err_msg})
            items_record.append({
                "from": str(src),
                "to": str(dest),
                "name": src.name,
                "rule": file_info.get("category", "기타"),
                "size": file_info.get("size", 0),
                "status": "failed",
                "error": err_msg
            })

    batch_entry = {
        "batchId": batch_id,
        "startedAt": started_at,
        "trigger": trigger,
        "count": moved_count,
        "items": items_record,
        "errors": errors,
        "undoneAt": None
    }

    return batch_entry


def undo_batch(batch_entry):
    """
    Reverts a specific batch of moved files.
    """
    reverted_count = 0
    errors = []

    for item in batch_entry.get("items", []):
        if item.get("status") != "ok":
            continue

        curr = pathlib.Path(item["to"])
        orig = pathlib.Path(item["from"])

        if not curr.exists():
            errors.append(f"이동된 파일이 현재 존재하지 않음: {curr.name}")
            continue

        # Check collision at original location
        target_dest = orig
        counter = 1
        while target_dest.exists():
            target_dest = orig.parent / f"{orig.stem} (복구_{counter}){orig.suffix}"
            counter += 1

        try:
            shutil.move(str(curr), str(target_dest))
            reverted_count += 1
        except Exception as e:
            errors.append(f"{curr.name} 복구 실패: {str(e)}")

    batch_entry["undoneAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "success": True,
        "reverted_count": reverted_count,
        "errors": errors
    }
