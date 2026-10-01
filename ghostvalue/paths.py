"""Local-only paths. Never require a contributor's machine-specific layout."""
import os
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ['GHOSTVALUE_DATA_DIR']).expanduser() if os.environ.get('GHOSTVALUE_DATA_DIR') else (
    PROJECT_ROOT / '.local' if (PROJECT_ROOT / 'pyproject.toml').exists()
    else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'GhostValue'
)


def game_executable():
    configured = os.environ.get('GHOSTVALUE_GAME_DIR')
    if configured:
        return Path(configured).expanduser() / 'Kingdom Rush Genesis.exe'
    libraries = [Path(r'D:\SteamLibrary'), Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Steam']
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
        libraries.insert(0, steam)
        folders = steam / 'steamapps' / 'libraryfolders.vdf'
        if folders.exists():
            text = folders.read_text(encoding='utf-8')
            libraries.extend(Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', text))
    except (ImportError, OSError):
        pass
    for library in libraries:
        candidate = library / 'steamapps' / 'common' / 'Kingdom Rush Genesis' / 'Kingdom Rush Genesis.exe'
        if candidate.exists():
            return candidate
    return libraries[0] / 'steamapps' / 'common' / 'Kingdom Rush Genesis' / 'Kingdom Rush Genesis.exe'
