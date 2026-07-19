import os
import sys
import codecs
from pathlib import Path
import shutil

CONFIG_DIR = Path.home() / ".config" / "vps-manager"
CONFIG_FILE = CONFIG_DIR / "servers.json"
SNIPPET_FILE = CONFIG_DIR / "snippets.json"

def supports_color() -> bool:
    """Mendeteksi ketersediaan dukungan warna terminal ANSI."""
    if "NO_COLOR" in os.environ:
        return False
    plat = sys.platform
    supported_platform = plat != 'win32' or 'ANSICON' in os.environ or 'WT_SESSION' in os.environ
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    return supported_platform and is_a_tty

def supports_unicode() -> bool:
    """Mendeteksi dukungan rendering karakter Unicode UTF-8 secara akurat."""
    try:
        codecs.lookup('utf-8')
        encoding = sys.stdout.encoding or 'ascii'
        return 'utf-8' in encoding.lower()
    except LookupError:
        return False

USE_COLOR = supports_color()
USE_UNICODE = supports_unicode()

CLR_RESET = "\033[0m" if USE_COLOR else ""
RESET = CLR_RESET 
CLR_RESET = "\033[0m" if USE_COLOR else ""
CLR_BOLD = "\033[1m" if USE_COLOR else ""
CLR_DIM = "\033[2m" if USE_COLOR else ""

CLR_RED = "\033[38;2;255;95;95m" if USE_COLOR else ""
CLR_GREEN = "\033[38;2;95;255;95m" if USE_COLOR else ""
CLR_YELLOW = "\033[38;2;255;215;0m" if USE_COLOR else ""
CLR_BLUE = "\033[38;2;95;175;255m" if USE_COLOR else ""
CLR_PURPLE = "\033[38;2;175;95;255m" if USE_COLOR else ""
CLR_CYAN = "\033[38;2;95;255;255m" if USE_COLOR else ""
CLR_GRAY = "\033[38;2;135;135;135m" if USE_COLOR else ""

if USE_UNICODE:
    B_TL, B_TR = "╭", "╮"
    B_BL, B_BR = "╰", "╯"
    B_H, B_V = "─", "│"
    B_L_DIV, B_R_DIV = "├", "┤"
    
    ICON_KEY = "🔑"
    ICON_PASS = "🔒"
    ICON_ONLINE = "🟢"
    ICON_OFFLINE = "🔴"
    ICON_SUCCESS = "✔"
    ICON_WARN = "⚠️"
    ICON_TAG = "🏷️"
    ICON_CPU = "📊"
    ICON_RAM = "💾"
    ICON_DISK = "💽"
    ICON_UPTIME = "⏱️"
else:
    B_TL, B_TR = "+", "+"
    B_BL, B_BR = "+", "+"
    B_H, B_V = "-", "|"
    B_L_DIV, B_R_DIV = "+", "+"
    
    ICON_KEY = "[Key]"
    ICON_PASS = "[Pass]"
    ICON_ONLINE = "[UP]"
    ICON_OFFLINE = "[DOWN]"
    ICON_SUCCESS = "[Y]"
    ICON_WARN = "[!]"
    ICON_TAG = "[Tag]"
    ICON_CPU = "[CPU]"
    ICON_RAM = "[RAM]"
    ICON_DISK = "[Disk]"
    ICON_UPTIME = "[Upt]"

def get_terminal_width(default: int = 80) -> int:
    """Mengembalikan dimensi lebar terminal saat eksekusi berjalan."""
    return shutil.get_terminal_size((default, 24)).columns

def init_storage():
    """Menginisialisasi seluruh pustaka penyimpanan lokal dengan hak akses terisolasi."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    for file, default_content in [(CONFIG_FILE, "[]"), (SNIPPET_FILE, "[]")]:
        if not file.exists():
            with open(file, "w", encoding="utf-8") as f:
                f.write(default_content)
            file.chmod(0o600)
