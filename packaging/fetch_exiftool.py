"""
Prepara o ExifTool em vendor/exiftool/ para o PyInstaller embutir.

    python packaging/fetch_exiftool.py

Roda igual nos dois sistemas, mas o que ele prepara é diferente:

  macOS/Linux  ExifTool é um script Perl. Precisa do script MAIS a pasta
               lib/ com os módulos (~20 MB). Roda com o Perl do sistema,
               que vem de fábrica no macOS.
  Windows      Não existe Perl de sistema. A distribuição oficial é um
               .exe autocontido — vai só ele.

Prefere uma instalação local já existente (é mais rápido e não depende
de rede); só baixa da exiftool.org se não achar nada.

Sem isto o app ainda constrói: apenas cai no ExifTool instalado na
máquina de quem usar, e mostra a instrução de instalação se não achar.
"""

import io
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "vendor" / "exiftool"

VERSAO = "13.59"
URL_UNIX = "https://exiftool.org/Image-ExifTool-%s.tar.gz" % VERSAO
URL_WINDOWS = "https://exiftool.org/exiftool-%s_64.zip" % VERSAO


def log(msg):
    print("  " + msg)


# ------------------------------------------------------------ instalação local

def achar_local_unix():
    """Uma instalação standalone tem o script e um lib/ ao lado dele."""
    caminho = shutil.which("exiftool")
    if not caminho:
        return None
    real = Path(caminho).resolve()
    lib = real.parent / "lib"
    if (lib / "Image" / "ExifTool.pm").is_file():
        return real, lib
    return None


def copiar_local_unix(script, lib):
    DESTINO.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(script), str(DESTINO / "exiftool"))
    os.chmod(str(DESTINO / "exiftool"), 0o755)
    alvo_lib = DESTINO / "lib"
    if alvo_lib.exists():
        shutil.rmtree(str(alvo_lib))
    shutil.copytree(str(lib), str(alvo_lib))
    log("copiado da instalação local: %s" % script)


# --------------------------------------------------------------- download

def baixar(url):
    log("baixando %s" % url)
    requisicao = urllib.request.Request(url, headers={"User-Agent": "CineBrainOS-build"})
    with urllib.request.urlopen(requisicao, timeout=120) as resposta:
        return resposta.read()


def preparar_unix():
    local = achar_local_unix()
    if local:
        copiar_local_unix(*local)
        return

    dados = baixar(URL_UNIX)
    DESTINO.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(dados), mode="r:gz") as tar:
        # o tarball vem com uma pasta raiz Image-ExifTool-X.YY/
        temporario = DESTINO.parent / "_exiftool_tmp"
        if temporario.exists():
            shutil.rmtree(str(temporario))
        tar.extractall(str(temporario))
        raiz = next(temporario.iterdir())
        shutil.copy2(str(raiz / "exiftool"), str(DESTINO / "exiftool"))
        os.chmod(str(DESTINO / "exiftool"), 0o755)
        alvo_lib = DESTINO / "lib"
        if alvo_lib.exists():
            shutil.rmtree(str(alvo_lib))
        shutil.copytree(str(raiz / "lib"), str(alvo_lib))
        shutil.rmtree(str(temporario))
    log("baixado e extraído")


def preparar_windows():
    dados = baixar(URL_WINDOWS)
    DESTINO.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(dados)) as zf:
        nomes = zf.namelist()
        # o zip oficial traz "exiftool(-k).exe" — o sufixo (-k) faz o
        # programa pausar esperando Enter, o que travaria o app
        alvo = next((n for n in nomes if n.lower().endswith(".exe")), None)
        if not alvo:
            raise RuntimeError("não achei o .exe dentro do zip do ExifTool")
        with zf.open(alvo) as origem, open(str(DESTINO / "exiftool.exe"), "wb") as saida:
            shutil.copyfileobj(origem, saida)
        # a partir da 12.x o zip traz uma pasta exiftool_files/ obrigatória
        pasta_extra = [n for n in nomes if "exiftool_files/" in n.replace("\\", "/")]
        for nome in pasta_extra:
            relativo = nome.replace("\\", "/").split("exiftool_files/", 1)[1]
            if not relativo:
                continue
            destino_arquivo = DESTINO / "exiftool_files" / relativo
            destino_arquivo.parent.mkdir(parents=True, exist_ok=True)
            if nome.endswith("/"):
                continue
            with zf.open(nome) as origem, open(str(destino_arquivo), "wb") as saida:
                shutil.copyfileobj(origem, saida)
    log("baixado e extraído")


# ------------------------------------------------------------------ prova

def conferir():
    binario = DESTINO / ("exiftool.exe" if sys.platform == "win32" else "exiftool")
    if not binario.is_file():
        log("FALHOU: %s não existe" % binario)
        return False
    try:
        # mesmo criterio do app: se o bit de execucao nao sobreviveu a
        # copia (volumes de nuvem descartam), chama via perl
        if sys.platform == "win32" or os.access(str(binario), os.X_OK):
            comando = [str(binario)]
        else:
            comando = ["perl", str(binario)]
        saida = subprocess.run(comando + ["-ver"], capture_output=True,
                               text=True, timeout=30)
        versao = saida.stdout.strip()
        if versao:
            log("conferido: ExifTool %s responde de dentro de vendor/" % versao)
            return True
        log("o binário existe mas não respondeu a -ver: %s" % saida.stderr.strip()[:120])
    except Exception as e:
        log("o binário existe mas não executou: %s" % e)
    return False


def main():
    print("Preparando ExifTool em %s" % DESTINO)
    if DESTINO.exists():
        shutil.rmtree(str(DESTINO))
    try:
        if sys.platform == "win32":
            preparar_windows()
        else:
            preparar_unix()
    except Exception as e:
        log("NÃO consegui preparar o ExifTool: %s" % e)
        log("O app ainda constrói — vai usar o ExifTool instalado na máquina")
        log("de quem usar, e avisa se não achar nenhum.")
        return 1
    return 0 if conferir() else 1


if __name__ == "__main__":
    sys.exit(main())
