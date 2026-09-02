# -*- mode: python ; coding: utf-8 -*-
"""
Receita do PyInstaller do Metadados 81 — macOS e Windows.

    pyinstaller packaging/cinebrain.spec --noconfirm

A v1.0 nao tinha esta receita versionada (o .gitignore engolia *.spec),
e por isso o DMG dela era irreproduzivel. Este arquivo existe para que
qualquer pessoa consiga reconstruir o app do zero.

O QUE VAI DENTRO DO PACOTE

  src/                 o codigo
  assets/fonts/        DM Sans e JetBrains Mono (a identidade visual
                       depende delas e nenhuma existe de fabrica nos
                       dois sistemas)
  tkinterdnd2/tkdnd/   os binarios de arrastar-e-soltar, um por
                       plataforma e arquitetura
  vendor/exiftool/     o ExifTool, se tiver sido preparado

SOBRE O EXIFTOOL — o ponto onde a v1.0 mentia

O comentario do codigo dizia que o ExifTool ia embutido. Nao ia: o .app
da v1.0 nao tem exiftool nenhum dentro, e o app dependia silenciosamente
do que estivesse instalado na maquina. Quem recebesse o DMG sem ExifTool
instalado descobriria isso so ao tentar gravar metadados.

Agora ele e embutido de verdade, mas a forma muda por sistema:

  macOS/Linux  ExifTool e um script Perl e roda com o Perl do sistema,
               que vem de fabrica no macOS. Vai a pasta inteira
               (exiftool + lib/), ~20 MB.
  Windows      NAO existe Perl de sistema. A distribuicao oficial e um
               .exe autocontido; vai so ele.

Rode `python packaging/fetch_exiftool.py` antes de empacotar para
preparar vendor/exiftool. Sem isso o app ainda constroi — apenas cai no
ExifTool do sistema, e avisa o usuario se nao achar nenhum.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

RAIZ = Path(SPECPATH).parent
SRC = RAIZ / "src"
VENDOR = RAIZ / "vendor"

APP_NAME = "Metadados 81"
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# --------------------------------------------------------------- dados

datas = []

# fontes embutidas — sem elas o app cai numa fonte de sistema e perde a
# identidade visual; a licenca OFL exige distribuir OFL.txt junto
pasta_fontes = RAIZ / "assets" / "fonts"
if pasta_fontes.is_dir():
    datas.append((str(pasta_fontes), "assets/fonts"))

# arrastar-e-soltar: o pacote traz um binario por plataforma/arquitetura
# (osx-arm64, osx-x64, win-x64, win-x86, linux-*). collect_data_files
# pega a arvore toda; deixar de fora a certa quebra o recurso em silencio
datas += collect_data_files("tkinterdnd2")

# ExifTool preparado por fetch_exiftool.py
pasta_exiftool = VENDOR / "exiftool"
if pasta_exiftool.is_dir():
    datas.append((str(pasta_exiftool), "exiftool_bundle"))

# --------------------------------------------------------------- icone

def _icone():
    extensao = ".ico" if IS_WINDOWS else ".icns"
    candidato = RAIZ / "assets" / ("icone" + extensao)
    return str(candidato) if candidato.is_file() else None


# ------------------------------------------------------------- analise

a = Analysis(
    [str(SRC / "app.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # importados dinamicamente ou so em ramo de plataforma, o que faz
        # o PyInstaller nao enxergar sozinho
        "tkinter", "tkinter.ttk", "tkinter.filedialog",
        "tkinter.messagebox", "tkinter.font",
        "PIL._tkinter_finder",
        "openpyxl", "reportlab", "piexif",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # o app nao usa nada disto e sao pesados
    excludes=["numpy", "pandas", "matplotlib", "scipy", "PyQt5", "PySide2",
              "IPython", "jupyter", "pytest", "setuptools", "pip"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME if not IS_WINDOWS else "Metadados81",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX corrompe binarios assinados no macOS
    console=False,       # app de janela: sem terminal preto atras
    disable_windowed_traceback=False,
    argv_emulation=IS_MACOS,   # permite abrir arquivos arrastados no Dock
    target_arch=None,          # segue a arquitetura de quem constroi
    codesign_identity=None,
    entitlements_file=None,
    icon=_icone(),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME if not IS_WINDOWS else "Metadados81",
)

if IS_MACOS:
    app = BUNDLE(
        coll,
        name=APP_NAME + ".app",
        icon=_icone(),
        bundle_identifier="com.cine81.metadados81",
        version="2.0.0",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": "2.0.0",
            "CFBundleVersion": "2.0.0",
            "NSHighResolutionCapable": True,
            # sem isto o macOS abre o app em modo retina emulado e a
            # interface sai borrada
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "CineBrain OS — MIT",
        },
    )
