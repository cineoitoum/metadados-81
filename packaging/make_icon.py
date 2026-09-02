"""
Gera o ícone do app a partir da paleta, em .icns (macOS) e .ico (Windows).

    python packaging/make_icon.py

Não existia ícone nenhum no projeto. Em vez de deixar o app com o ícone
genérico do Python, desenha a marca: um bloco arredondado steel com o
recorte peach do pôster de referência.

Precisa só do Pillow, que já é dependência do app.
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "assets"

STEEL = (63, 90, 98)
PEACH = (254, 130, 84)
CREME = (228, 220, 201)


def desenhar(tamanho):
    """O bloco steel com o quadrado peach encaixado no canto — o gesto do
    pôster reduzido ao que ainda se lê em 16px."""
    escala = 4
    lado = tamanho * escala
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    margem = int(lado * 0.06)
    raio = int(lado * 0.22)
    d.rounded_rectangle([margem, margem, lado - margem, lado - margem],
                        radius=raio, fill=CREME)

    # bloco steel ocupando o corpo
    m2 = int(lado * 0.16)
    d.rounded_rectangle([m2, m2, lado - m2, int(lado * 0.66)],
                        radius=int(lado * 0.11), fill=STEEL)

    # bloco peach encaixado embaixo, deslocado — o "encaixe" do pôster
    d.rounded_rectangle([int(lado * 0.34), int(lado * 0.56),
                         lado - m2, lado - m2],
                        radius=int(lado * 0.11), fill=PEACH)

    return img.resize((tamanho, tamanho), Image.LANCZOS)


def gerar_ico():
    destino = ASSETS / "icone.ico"
    tamanhos = [16, 24, 32, 48, 64, 128, 256]
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
