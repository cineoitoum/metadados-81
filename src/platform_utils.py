"""
Camada de abstração de sistema operacional do Metadados 81.

Todo ponto onde o app precisa saber em que sistema está rodando mora
aqui — e só aqui. As engines e as abas chamam estas funções e não
importam `sys.platform` diretamente.

Cobre:
  - onde ficam os dados do app (Application Support / APPDATA / .config)
  - nome do HD/volume de um caminho (diskutil / letra de unidade)
  - abrir uma pasta no gerenciador de arquivos (Finder / Explorer)
  - famílias de fonte disponíveis por sistema

Nenhuma função aqui levanta exceção por estar no sistema "errado": todas
degradam pra um comportamento razoável. Um app que não consegue
descobrir o nome do volume deve continuar funcionando, só com um rótulo
genérico.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

APP_NAME = "Metadados 81"

# nome da pasta de dados usada pela v1.0 (Metadata Foto 81), pra migração
# a pasta da v1.0, de onde as preferências de metadados podem vir
LEGACY_APP_FOLDER = "Metadata Foto 81"


# ------------------------------------------------------------- plataforma

def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def platform_label() -> str:
    if is_macos():
        return "macOS"
    if is_windows():
        return "Windows"
    if is_linux():
        return "Linux"
    return sys.platform


# --------------------------------------------------- pasta de dados do app

def get_app_dir(app_name: str = APP_NAME) -> str:
    """Pasta de dados da aplicação, criada se não existir.

        macOS    ~/Library/Application Support/CineBrain OS
        Windows  %APPDATA%\\CineBrain OS
        Linux    ~/.config/CineBrain OS   (respeita XDG_CONFIG_HOME)

    Retorna str (e não Path) porque o resto da base usa os.path.* — mas
    a montagem é feita com pathlib, sem concatenar barra em lugar nenhum.
    """
    if is_macos():
        base = Path.home() / "Library" / "Application Support"
    elif is_windows():
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"

    target = base / app_name
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        # disco cheio, permissão negada, volume somente-leitura: cai pra
        # pasta pessoal, que sempre existe e é gravável
        target = Path.home()
    return str(target)


def get_legacy_app_dir() -> Optional[str]:
    """Pasta de dados da v1.0 (Metadata Foto 81), se existir. Usada uma
    única vez pela migração. Não cria nada."""
    if is_macos():
        base = Path.home() / "Library" / "Application Support"
    elif is_windows():
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
    candidate = base / LEGACY_APP_FOLDER
    return str(candidate) if candidate.is_dir() else None


def default_documents_dir() -> str:
    """Sugestão inicial de pasta administrativa no primeiro uso."""
    for name in ("Documents", "Documentos"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return str(candidate)
    return str(Path.home())


# --------------------------------------------------------- volumes / discos

def get_volume_name(path: str) -> str:
    """Nome legível do HD/volume onde 'path' está.

    macOS   : /Volumes/X/... -> "X"; senão pergunta ao diskutil
    Windows : rótulo do volume via API do Windows; senão "Disco D:"
    Linux   : ponto de montagem em /media|/mnt; senão "Sistema de arquivos"
    """
    if is_macos():
        return _volume_name_macos(path)
    if is_windows():
        return _volume_name_windows(path)
    return _volume_name_linux(path)


def _real(path: str) -> str:
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def _volume_name_macos(path: str) -> str:
    real = _real(path)
    parts = Path(real).parts
    # ('/', 'Volumes', 'NOME', ...) -> volume externo montado
    if len(parts) > 2 and parts[1] == "Volumes":
        return parts[2]
    try:
        import plistlib
        out = subprocess.run(
            ["diskutil", "info", "-plist", "/"],
            capture_output=True, timeout=5,
        )
        if out.returncode == 0:
            name = plistlib.loads(out.stdout).get("VolumeName")
            if name:
                return name
    except Exception:
        pass
    return "Macintosh HD"


def _volume_name_windows(path: str) -> str:
    drive, _rest = os.path.splitdrive(_real(path))
    if not drive:
        return "Disco local"
    # Tenta o rótulo real do volume pela API do Windows. Usa ctypes em vez
    # de psutil pra não acrescentar dependência só por causa disso.
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(261)
        fs_buf = ctypes.create_unicode_buffer(261)
        root = drive if drive.endswith("\\") else drive + "\\"
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), buf, ctypes.sizeof(buf),
            None, None, None, fs_buf, ctypes.sizeof(fs_buf),
        )
        if ok and buf.value.strip():
            return "%s (%s)" % (buf.value.strip(), drive)
    except Exception:
        pass
    return "Disco %s" % drive


def _volume_name_linux(path: str) -> str:
    real = _real(path)
    parts = Path(real).parts
    # ('/', 'media', 'usuario', 'NOME', ...) ou ('/', 'mnt', 'NOME', ...)
    if len(parts) > 2 and parts[1] in ("media", "mnt", "run"):
        if parts[1] == "media" and len(parts) > 3:
            return parts[3]
        if len(parts) > 2:
            return parts[2]
    return "Sistema de arquivos"


def list_removable_volumes() -> List[str]:
    """Volumes montados que provavelmente são cartão/HD externo. Usado pra
    sugerir a origem no Ingest. Lista vazia é resposta válida."""
    found = []
    if is_macos():
        vol_root = Path("/Volumes")
        if vol_root.is_dir():
            try:
                found = [str(p) for p in vol_root.iterdir() if p.is_dir()]
            except OSError:
                found = []
    elif is_windows():
        try:
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    letter = "%s:\\" % chr(ord("A") + i)
                    # 2 = DRIVE_REMOVABLE, 3 = DRIVE_FIXED
                    kind = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letter))
                    if kind in (2, 3) and letter.upper() != "C:\\":
                        found.append(letter)
        except Exception:
            found = []
    else:
        for base in ("/media", "/run/media", "/mnt"):
            root = Path(base)
            if root.is_dir():
                try:
                    for p in root.iterdir():
                        if p.is_dir():
                            found.append(str(p))
                except OSError:
                    pass
    return sorted(found)


# --------------------------------------------- gerenciador de arquivos

def open_in_file_manager(path: str) -> bool:
    """Abre a pasta no Finder/Explorer/gerenciador do sistema.
    Retorna False se não conseguiu — o chamador decide se avisa."""
    if not path or not os.path.exists(path):
        return False
    try:
        if is_macos():
            subprocess.run(["open", path], timeout=10)
        elif is_windows():
            # os.startfile só existe no Windows; é o caminho canônico
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], timeout=10)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ fontes

# O CineBrain OS embute DM Sans e JetBrains Mono porque NENHUMA das duas
# existe de fábrica no macOS ou no Windows, e a identidade visual depende
# delas. São registradas só para o processo — nada é instalado no sistema
# de quem usa o app.
#
# ORDEM IMPORTA: o registro precisa acontecer ANTES de o Tk inicializar.
# O Tk monta a lista de famílias na criação do interpretador; registrar
# depois retorna sucesso e mesmo assim a fonte não aparece. Por isso
# register_bundled_fonts() é a primeira coisa que main() faz.

BUNDLED_FONTS = {
    "DM Sans": "DMSans.ttf",
    "JetBrains Mono": "JetBrainsMono.ttf",
}

# Usadas se o registro falhar. Não são bonitas — são o que existe nos dois
# sistemas — mas mantêm o app legível em vez de deixar o Tk escolher.
UI_FONT_CANDIDATES = {
    "darwin": ["DM Sans", "Helvetica Neue", "Lucida Grande", "Helvetica"],
    "win32": ["DM Sans", "Segoe UI", "Tahoma", "Arial"],
    "linux": ["DM Sans", "Cantarell", "DejaVu Sans", "Liberation Sans"],
}

MONO_FONT_CANDIDATES = {
    "darwin": ["JetBrains Mono", "SF Mono", "Menlo", "Monaco", "Courier New"],
    "win32": ["JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New"],
    "linux": ["JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Courier New"],
}


def bundled_fonts_dir() -> str:
    """assets/fonts, tanto rodando do código-fonte quanto empacotado."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return str(Path(base) / "assets" / "fonts")
    # src/platform_utils.py -> sobe pra raiz do projeto
    return str(Path(__file__).resolve().parent.parent / "assets" / "fonts")


_fontes_registradas = None


def register_bundled_fonts() -> List[str]:
    """Registra as fontes embutidas. Devolve as famílias que entraram.

    IDEMPOTENTE de propósito: registrar a mesma fonte duas vezes faz a
    API do sistema devolver falso (macOS diz "já registrada"), o que
    daria a impressão de falha na segunda chamada. Como main() e o
    smoke-test chamam esta função, o resultado da primeira vez fica
    guardado e é reaproveitado.

    Falha aqui NUNCA é fatal: sem as fontes o app fica menos bonito, e o
    theme cai na próxima família disponível da lista de candidatos."""
    global _fontes_registradas
    if _fontes_registradas is not None:
        return list(_fontes_registradas)

    pasta = Path(bundled_fonts_dir())
    if not pasta.is_dir():
        _fontes_registradas = []
        return []

    registradas = []
    for familia, arquivo in BUNDLED_FONTS.items():
        caminho = pasta / arquivo
        if not caminho.is_file():
            continue
        try:
            if _register_font_file(str(caminho)):
                registradas.append(familia)
        except Exception:
            pass
    _fontes_registradas = registradas
    return list(registradas)


def _register_font_file(path: str) -> bool:
    if is_macos():
        return _register_font_macos(path)
    if is_windows():
        return _register_font_windows(path)
    return _register_font_linux(path)


def _register_font_macos(path: str) -> bool:
    """CoreText, no escopo do processo — não mexe na Central de Fontes."""
    import ctypes
    import ctypes.util

    coretext = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))
    corefoundation = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))

    corefoundation.CFStringCreateWithCString.restype = ctypes.c_void_p
    corefoundation.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    corefoundation.CFURLCreateWithFileSystemPath.restype = ctypes.c_void_p
    corefoundation.CFURLCreateWithFileSystemPath.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_bool]
    coretext.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
    coretext.CTFontManagerRegisterFontsForURL.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]

    K_CF_STRING_ENCODING_UTF8 = 0x08000100
    K_CT_FONT_MANAGER_SCOPE_PROCESS = 1

    texto = corefoundation.CFStringCreateWithCString(
        None, path.encode("utf-8"), K_CF_STRING_ENCODING_UTF8)
    url = corefoundation.CFURLCreateWithFileSystemPath(None, texto, 0, False)
    return bool(coretext.CTFontManagerRegisterFontsForURL(
        url, K_CT_FONT_MANAGER_SCOPE_PROCESS, None))


def _register_font_windows(path: str) -> bool:
    """AddFontResourceEx com FR_PRIVATE: visível só para este processo."""
    import ctypes
    FR_PRIVATE = 0x10
    adicionadas = ctypes.windll.gdi32.AddFontResourceExW(
        ctypes.c_wchar_p(path), FR_PRIVATE, 0)
    return adicionadas > 0


def _register_font_linux(path: str) -> bool:
    """Fontconfig não tem registro por processo. Copia pra pasta de fontes
    do usuário e atualiza o cache — só na primeira execução."""
    import shutil
    import subprocess

    destino_dir = Path.home() / ".local" / "share" / "fonts" / APP_NAME
    destino = destino_dir / Path(path).name
    if destino.is_file():
        return True
    try:
        destino_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, str(destino))
        subprocess.run(["fc-cache", "-f", str(destino_dir)],
                       capture_output=True, timeout=30)
        return True
    except Exception:
        return False


def _candidates(table: dict) -> List[str]:
    if is_macos():
        return table["darwin"]
    if is_windows():
        return table["win32"]
    return table["linux"]


def ui_font_candidates() -> List[str]:
    return list(_candidates(UI_FONT_CANDIDATES))


def mono_font_candidates() -> List[str]:
    return list(_candidates(MONO_FONT_CANDIDATES))


# ---------------------------------------------------------------- ExifTool

def exiftool_bundle_name() -> str:
    """Nome do executável do ExifTool dentro do bundle do PyInstaller.

    No macOS o ExifTool distribuído é um script Perl e roda com o Perl do
    sistema (presente de fábrica). No Windows não existe Perl de sistema —
    a distribuição oficial é um .exe autocontido. Por isso o nome muda.
    """
    return "exiftool.exe" if is_windows() else "exiftool"


def exiftool_command(binary: str) -> List[str]:
    """Como INVOCAR o ExifTool encontrado.

    No macOS e no Linux o ExifTool e um script Perl. Se ele estiver sem
    bit de execucao, chamar direto da "Permission denied" — e isso
    acontece de verdade: volumes de nuvem (pCloud, Drive, Dropbox) e
    alguns descompactadores descartam o bit em silencio, e o PyInstaller
    nao garante preserva-lo ao copiar arquivos de dados.

    Chamar `perl script` contorna tudo isso e funciona igual. O script
    acha os proprios modulos com FindBin, entao a pasta lib/ ao lado
    continua sendo encontrada.

    No Windows a distribuicao e um .exe autocontido e nao existe bit de
    execucao — vai direto.
    """
    if is_windows():
        return [binary]
    if os.access(binary, os.X_OK):
        return [binary]
    return ["perl", binary]


def exiftool_fallback_paths() -> List[str]:
    """Locais prováveis do ExifTool instalado no sistema, por plataforma."""
    if is_windows():
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        return [
            str(Path(program_files) / "ExifTool" / "exiftool.exe"),
            str(Path(program_files_x86) / "ExifTool" / "exiftool.exe"),
            str(Path.home() / "scoop" / "shims" / "exiftool.exe"),
            r"C:\exiftool\exiftool.exe",
        ]
    if is_macos():
        return [
            "/usr/local/bin/exiftool",
            "/opt/homebrew/bin/exiftool",
            "/usr/bin/exiftool",
        ]
    return [
        "/usr/bin/exiftool",
        "/usr/local/bin/exiftool",
        "/snap/bin/exiftool",
    ]


def exiftool_install_hint() -> str:
    """Instrução de instalação adequada ao sistema de quem está usando."""
    if is_windows():
        return (
            "ExifTool não encontrado. Baixe o pacote para Windows em "
            "https://exiftool.org, extraia e renomeie "
            "\"exiftool(-k).exe\" para \"exiftool.exe\"."
        )
    if is_macos():
        return (
            "ExifTool não encontrado. Instale com \"brew install exiftool\" "
            "ou baixe o instalador em https://exiftool.org."
        )
    return (
        "ExifTool não encontrado. Instale pelo gerenciador de pacotes da sua "
        "distribuição (ex.: \"sudo apt install libimage-exiftool-perl\")."
    )


# --------------------------------------------------- subprocessos silenciosos

def subprocess_flags() -> dict:
    """kwargs extras pro subprocess.run não piscar console no Windows.
    Em macOS/Linux devolve dict vazio."""
    if is_windows():
        # CREATE_NO_WINDOW — evita a janelinha preta a cada chamada do ExifTool
        return {"creationflags": 0x08000000}
    return {}
