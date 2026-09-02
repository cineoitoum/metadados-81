"""
Gera o ícone do app em pixel art, em .icns (macOS) e .ico (Windows).

    python packaging/make_icon.py

O desenho É a grade de 16x16 do MAPA abaixo: cada caractere é um pixel.
Todos os tamanhos que os dois sistemas pedem (16, 32, 48, 64, 128, 256,
512, 1024) são múltiplos inteiros de 16, então a ampliação usa NEAREST
e sai exata — sem borda embaçada e sem meio-pixel. É por isso que o
ícone de 16px continua legível: ele não é uma redução de um desenho
grande, é o desenho original.

Precisa só do Pillow, que já é dependência do app.
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "assets"


# ---------------------------------------------------------------- paleta
CORES = {
    ".": (0, 0, 0, 0),          # vazio
    "K": (34, 51, 58, 255),     # contorno, quase preto azulado
    "T": (122, 146, 152, 255),  # chapa de cima, steel clareado
    "S": (63, 90, 98, 255),     # corpo, steel
    "P": (254, 130, 84, 255),   # aro da lente, peach
    "D": (44, 65, 73, 255),     # vidro da lente
    "W": (150, 180, 188, 255),  # reflexo no vidro, azul claro
}

# Câmera de frente: chapa de cima mais clara, visor saliente, lente
# centrada com dois pixels de reflexo no canto superior esquerdo do
# vidro. Creme puro no reflexo lia como buraco — daí o azul claro.
MAPA = [
    "................",
    "....KKKK........",
    "...KTTTTK.......",
    ".KKKTTTTKKKKKKK.",
    "KTTTTTTTTTTTTTTK",
    "KSSSSSSSSSSSSSSK",
    "KSSSSSPPPSSSSSSK",
    "KSSSSPDWDPSSSSSK",
    "KSSSPDWDDDPSSSSK",
    "KSSSPDDDDDPSSSSK",
    "KSSSPDDDDDPSSSSK",
    "KSSSSPDDDPSSSSSK",
    "KSSSSSPPPSSSSSSK",
    "KSSSSSSSSSSSSSSK",
    ".KKKKKKKKKKKKKK.",
    "................",
]

LADO = len(MAPA)


def _base() -> Image.Image:
    """A grade crua, 16x16, um pixel por caractere."""
    img = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    px = img.load()
    for y, linha in enumerate(MAPA):
        if len(linha) != LADO:
            raise ValueError("linha %d tem %d colunas, esperava %d"
                             % (y, len(linha), LADO))
        for x, ch in enumerate(linha):
            px[x, y] = CORES[ch]
    return img


def desenhar(tamanho: int) -> Image.Image:
    """Amplia por inteiro sempre que der (16, 32, 64...). Só cai no
    LANCZOS em tamanho que não seja múltiplo de 16, o que na prática
    nenhum sistema pede."""
    base = _base()
    if tamanho % LADO == 0:
        return base.resize((tamanho, tamanho), Image.NEAREST)
    return base.resize((tamanho, tamanho), Image.LANCZOS)


def gerar_ico():
    destino = ASSETS / "icone.ico"
    tamanhos = [16, 32, 48, 64, 128, 256]
    imagens = [desenhar(t) for t in tamanhos]
    imagens[0].save(str(destino), format="ICO",
                    sizes=[(t, t) for t in tamanhos], append_images=imagens[1:])
    print("  .ico  -> %s" % destino)


def gerar_icns():
    """iconutil só existe no macOS; em outros sistemas grava um PNG grande
    para quem for construir no Mac converter."""
    destino = ASSETS / "icone.icns"
    if sys.platform != "darwin":
        png = ASSETS / "icone_1024.png"
        desenhar(1024).save(str(png))
        print("  .icns só se gera no macOS; salvei %s" % png)
        return

    conjunto = ASSETS / "icone.iconset"
    conjunto.mkdir(parents=True, exist_ok=True)
    for tamanho in (16, 32, 64, 128, 256, 512):
        desenhar(tamanho).save(str(conjunto / ("icon_%dx%d.png" % (tamanho, tamanho))))
        desenhar(tamanho * 2).save(str(conjunto / ("icon_%dx%d@2x.png" % (tamanho, tamanho))))
    subprocess.run(["iconutil", "-c", "icns", str(conjunto), "-o", str(destino)],
                   check=True)
    for arquivo in conjunto.iterdir():
        arquivo.unlink()
    conjunto.rmdir()
    print("  .icns -> %s" % destino)


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    print("Gerando ícones em %s" % ASSETS)
    gerar_ico()
    gerar_icns()
