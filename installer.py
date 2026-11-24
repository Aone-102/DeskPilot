# -*- coding: utf-8 -*-
"""
DeskPilot v2.0 - Standalone One-Click Installer
Extracts embedded payload to %LOCALAPPDATA%\\Programs\\DeskPilot,
creates Desktop/Start Menu/Startup shortcuts, registers in Windows Add/Remove programs,
and launches DeskPilot.
"""

import os
import sys
import zipfile
import shutil
import subprocess
import threading
import winreg
import webbrowser

def get_base_dir():
    """Returns directory of embedded PyInstaller resources or script directory."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_install_dir():
    """Returns %LOCALAPPDATA%\\Programs\\DeskPilot."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(local_app_data, "Programs", "DeskPilot")

def create_shortcut(target, lnk_path, args="", desc="", icon=""):
    """Creates a Windows .lnk shortcut using PowerShell COM object."""
    try:
        os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
        target_clean = target.replace("'", "''")
        lnk_clean = lnk_path.replace("'", "''")
        args_clean = args.replace("'", "''")
        desc_clean = desc.replace("'", "''")
        icon_clean = icon.replace("'", "''")

        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{lnk_clean}'); "
            f"$s.TargetPath = '{target_clean}'; "
            f"$s.Arguments = '{args_clean}'; "
            f"$s.Description = '{desc_clean}'; "
        )
        if icon_clean:
            ps_cmd += f"$s.IconLocation = '{icon_clean}'; "
        ps_cmd += "$s.Save()"

        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
    except Exception as e:
        print(f"Shortcut creation error: {e}")

def register_uninstaller(install_dir, exe_path, uninstaller_path):
    """Registers application in Windows Current User Uninstall Registry."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DeskPilot"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "DeskPilot v2.0")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "2.0.0")
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "DeskPilot Team")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}"')
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, f'"{exe_path}",0')
            winreg.SetValueEx(key, "HelpLink", 0, winreg.REG_SZ, "https://github.com/Aone-102/DeskPilot")
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception as e:
        print(f"Registry uninstaller error: {e}")

def create_uninstall_bat(install_dir):
    """Creates a standalone uninstall.bat script in the install directory."""
    bat_content = """@echo off
chcp 65001 > nul
title DeskPilot 삭제 관리자
echo ========================================================
echo              DeskPilot v2.0 프로그램 삭제
echo ========================================================
echo.
echo DeskPilot v2.0을 컴퓨터에서 완전히 삭제하시겠습니까?
echo (참고: 기존 사용자의 할 일, 메모 데이터는 안전하게 보존됩니다.)
echo.
set /p CONFIRM="삭제를 계속 진행하려면 Y를 입력하세요 (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo 삭제가 취소되었습니다.
    timeout /t 2 > nul
    exit /b
)

echo.
echo [1/4] 실행 중인 DeskPilot 프로세스 종료 중...
taskkill /F /IM DeskPilot.exe 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq DeskPilot*" 2>nul

echo [2/4] 바로가기 아이콘 제거 중...
del /f /q "%USERPROFILE%\\Desktop\\DeskPilot.lnk" 2>nul
del /f /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\DeskPilot.lnk" 2>nul
del /f /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\DeskPilot.lnk" 2>nul

echo [3/4] 윈도우 프로그램 등록 정보 제거 중...
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeskPilot" /f 2>nul

echo [4/4] 프로그램 설치 폴더 삭제 예약 중...
timeout /t 1 > nul
start "" cmd /c "timeout /t 2 > nul & rmdir /s /q \\"%~dp0\\" & echo DeskPilot 삭제가 완료되었습니다. & pause"
exit
"""
    uninst_path = os.path.join(install_dir, "uninstall.bat")
    with open(uninst_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    return uninst_path

def perform_installation(chk_desktop, chk_startmenu, chk_startup, chk_launch, update_progress=None):
    """Core installation procedure."""
    def log(msg, pct):
        if update_progress:
            update_progress(msg, pct)
        else:
            print(f"[{pct}%] {msg}")

    log("기존 프로세스 확인 및 종료 중...", 10)
    subprocess.run(["taskkill", "/F", "/IM", "DeskPilot.exe"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    install_dir = get_install_dir()
    os.makedirs(install_dir, exist_ok=True)

    base_dir = get_base_dir()
    payload_zip = os.path.join(base_dir, "payload.zip")

    log("프로그램 파일 압축 해제 및 복사 중...", 30)
    if os.path.exists(payload_zip):
        with zipfile.ZipFile(payload_zip, 'r') as zf:
            zf.extractall(install_dir)
    else:
        # Fallback if unzipped payload exists in base_dir
        for item in os.listdir(base_dir):
            if item in ("DeskPilot.exe", "_internal", "static"):
                s = os.path.join(base_dir, item)
                d = os.path.join(install_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)

    exe_path = os.path.join(install_dir, "DeskPilot.exe")

    log("삭제 관리자 및 시스템 등록 정보 생성 중...", 60)
    uninst_bat = create_uninstall_bat(install_dir)
    register_uninstaller(install_dir, exe_path, uninst_bat)

    log("바로가기 및 시작 메뉴 등록 중...", 80)
    user_desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    user_startmenu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
    user_startup = os.path.join(user_startmenu, "Startup")

    if chk_desktop:
        create_shortcut(exe_path, os.path.join(user_desktop, "DeskPilot.lnk"), desc="DeskPilot 스마트 데스크탑 비서")

    if chk_startmenu:
        create_shortcut(exe_path, os.path.join(user_startmenu, "DeskPilot.lnk"), desc="DeskPilot 스마트 데스크탑 비서")

    if chk_startup:
        create_shortcut(exe_path, os.path.join(user_startup, "DeskPilot.lnk"), desc="DeskPilot 부팅 자동실행")

    log("설치 완료!", 100)

    if chk_launch and os.path.exists(exe_path):
        subprocess.Popen([exe_path], cwd=install_dir)
        webbrowser.open("http://localhost:48290")

def run_gui():
    """Tkinter-based modern GUI installer."""
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title("DeskPilot v2.0 설치 관리자")
    root.geometry("520x460")
    root.resizable(False, False)
    root.configure(bg="#0f172a")  # Slate 900

    # Center window
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Header Card
    header_frame = tk.Frame(root, bg="#1e293b", padx=24, pady=18)
    header_frame.pack(fill="x")

    lbl_title = tk.Label(header_frame, text="🚀 DeskPilot v2.0 설치", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg="#1e293b")
    lbl_title.pack(anchor="w")

    lbl_sub = tk.Label(header_frame, text="스마트 데스크탑 비서 & 스마트폰 무선 연동 올인원 앱", font=("Malgun Gothic", 10), fg="#94a3b8", bg="#1e293b")
    lbl_sub.pack(anchor="w", pady=(4, 0))

    # Content Frame
    content_frame = tk.Frame(root, bg="#0f172a", padx=24, pady=16)
    content_frame.pack(fill="both", expand=True)

    install_dir = get_install_dir()
    lbl_path_title = tk.Label(content_frame, text="설치 위치:", font=("Malgun Gothic", 10, "bold"), fg="#e2e8f0", bg="#0f172a")
    lbl_path_title.pack(anchor="w")

    path_box = tk.Frame(content_frame, bg="#1e293b", padx=12, pady=8, highlightbackground="#334155", highlightthickness=1)
    path_box.pack(fill="x", pady=(4, 16))
    lbl_path = tk.Label(path_box, text=install_dir, font=("Consolas", 9), fg="#38bdf8", bg="#1e293b", anchor="w")
    lbl_path.pack(fill="x")

    # Options Checkboxes
    var_desktop = tk.BooleanVar(value=True)
    var_startmenu = tk.BooleanVar(value=True)
    var_startup = tk.BooleanVar(value=True)
    var_launch = tk.BooleanVar(value=True)

    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Dark.TCheckbutton", background="#0f172a", foreground="#e2e8f0", font=("Malgun Gothic", 10))

    cb_desktop = ttk.Checkbutton(content_frame, text="바탕화면에 DeskPilot 바로가기 아이콘 생성", variable=var_desktop, style="Dark.TCheckbutton")
    cb_desktop.pack(anchor="w", pady=2)

    cb_startmenu = ttk.Checkbutton(content_frame, text="시작 메뉴(Programs)에 바로가기 등록", variable=var_startmenu, style="Dark.TCheckbutton")
    cb_startmenu.pack(anchor="w", pady=2)

    cb_startup = ttk.Checkbutton(content_frame, text="윈도우 부팅 시 백그라운드로 자동 실행 등록", variable=var_startup, style="Dark.TCheckbutton")
    cb_startup.pack(anchor="w", pady=2)

    cb_launch = ttk.Checkbutton(content_frame, text="설치 완료 후 DeskPilot 즉시 실행", variable=var_launch, style="Dark.TCheckbutton")
    cb_launch.pack(anchor="w", pady=2)

    # Progress & Status
    progress_frame = tk.Frame(content_frame, bg="#0f172a", pady=12)
    progress_frame.pack(fill="x")

    lbl_status = tk.Label(progress_frame, text="원클릭으로 설치하려면 아래 버튼을 누르세요.", font=("Malgun Gothic", 9), fg="#94a3b8", bg="#0f172a")
    lbl_status.pack(anchor="w", pady=(0, 4))

    style.configure("Indigo.Horizontal.TProgressbar", troughcolor="#1e293b", background="#6366f1", thickness=8)
    prog_bar = ttk.Progressbar(progress_frame, style="Indigo.Horizontal.TProgressbar", orient="horizontal", mode="determinate", maximum=100)
    prog_bar.pack(fill="x")

    # Button Bar
    btn_frame = tk.Frame(root, bg="#1e293b", padx=24, pady=14)
    btn_frame.pack(fill="x", side="bottom")

    btn_cancel = tk.Button(btn_frame, text="취소", font=("Malgun Gothic", 10), fg="#94a3b8", bg="#334155", activebackground="#475569", activeforeground="#ffffff", relief="flat", padx=16, pady=6, cursor="hand2", command=root.destroy)
    btn_cancel.pack(side="left")

    def on_install_click():
        btn_install.config(state="disabled", text="설치 진행 중...")
        btn_cancel.config(state="disabled")
        cb_desktop.config(state="disabled")
        cb_startmenu.config(state="disabled")
        cb_startup.config(state="disabled")
        cb_launch.config(state="disabled")

        def worker():
            def update_ui(msg, pct):
                root.after(0, lambda: [lbl_status.config(text=msg, fg="#38bdf8"), prog_bar.configure(value=pct)])

            perform_installation(
                var_desktop.get(),
                var_startmenu.get(),
                var_startup.get(),
                var_launch.get(),
                update_progress=update_ui
            )

            def finish():
                lbl_status.config(text="✨ DeskPilot v2.0 설치가 성공적으로 완료되었습니다!", fg="#34d399")
                btn_install.config(state="normal", text="완료", bg="#10b981", command=root.destroy)
                messagebox.showinfo("설치 완료", "DeskPilot v2.0 설치가 완료되었습니다!\n대시보드가 웹 브라우저에서 실행됩니다.")
                root.destroy()

            root.after(800, finish)

        threading.Thread(target=worker, daemon=True).start()

    btn_install = tk.Button(btn_frame, text="🚀 지금 설치하기 (원클릭 자동 설치)", font=("Malgun Gothic", 10, "bold"), fg="#ffffff", bg="#6366f1", activebackground="#4f46e5", activeforeground="#ffffff", relief="flat", padx=20, pady=6, cursor="hand2", command=on_install_click)
    btn_install.pack(side="right")

    root.mainloop()

def main():
    # Silent install switch: /S or /silent
    args_lower = [a.lower() for a in sys.argv]
    if "/s" in args_lower or "/silent" in args_lower or "/verysilent" in args_lower or "/q" in args_lower:
        perform_installation(True, True, True, True)
    else:
        run_gui()

if __name__ == "__main__":
    main()
