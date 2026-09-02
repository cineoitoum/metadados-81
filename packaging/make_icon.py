"""
Gera o ícone do app a partir da paleta, em .icns (macOS) e .ico (Windows).

    python packaging/make_icon.py

A marca: uma câmera formada por duas penas espelhadas — o que o app faz,
reduzido a uma forma só. O corpo e o prisma em steel, a lente em peach,
o chão em creme; a mesma paleta da interface (src/theme.py).

Tudo é desenhado em coordenadas normalizadas (0..1) e só no fim
multiplicado pelo lado, então a marca sai idêntica em 16px e em 1024px.

Precisa só do Pillow, que já é dependência do app.
"""

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "assets"

STEEL = (63, 90, 98)
PEACH = (254, 130, 84)
CREME = (228, 220, 201)
SUPER = 8  # o Draw do Pillow não tem antialiasing; resolve no downscale


def _pena(largura, comprimento, corte=True):
    """Silhueta de bico de pena no eixo local: (0,0) é o centro da base,
    +y desce até a ponta. Base reta, laterais que afunilam, ombro em 0.55
    e ponta única — é o ombro que faz o olho ler 'pena' e não 'triângulo'.
    """
    m = largura / 2
    corpo = [
        (-m, 0.0), (m, 0.0),
        (m * 0.62, comprimento * 0.55),
        (0.0, comprimento),
        (-m * 0.62, comprimento * 0.55),
    ]
    if not corte:
        return corpo, None
    s = largura * 0.11
    fenda = [
        (-s, comprimento * 0.30), (s, comprimento * 0.30),
        (s, comprimento * 0.80), (0.0, comprimento * 0.97),
        (-s, comprimento * 0.80),
    ]
    return corpo, fenda


def _situar(pontos, angulo, cx, cy, lado):
    """Gira em torno da base e leva pro lugar, já em pixels."""
    a = math.radians(angulo)
    cos_a, sin_a = math.cos(a), math.sin(a)
    return [(((x * cos_a - y * sin_a) + cx) * lado,
             ((x * sin_a + y * cos_a) + cy) * lado) for x, y in pontos]


def desenhar(tamanho, fundo=True):
    # abaixo de 32px a fenda da pena vira sujeira: some com ela
    detalhe = tamanho >= 32
    lado = tamanho * SUPER
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def R(x0, y0, x1, y1):
        return [x0 * lado, y0 * lado, x1 * lado, y1 * lado]

    if fundo:
        d.rounded_rectangle(R(0.015, 0.015, 0.985, 0.985),
                            radius=lado * 0.225, fill=CREME)

    fenda_c = 0.022          # respiro creme entre as duas metades
    corpo_y0, corpo_y1 = 0.395, 0.715
    prisma_y0 = 0.320
    raio = lado * 0.055

    for espelho in (False, True):
        sinal = -1 if espelho else 1

        def X(v):
            return 0.5 + sinal * (v - 0.5)

        x_out, x_in = X(0.150), X(0.5 - fenda_c / 2)
        esq, dir_ = min(x_out, x_in), max(x_out, x_in)

        # corpo
        d.rounded_rectangle(R(esq, corpo_y0, dir_, corpo_y1),
                            radius=raio, fill=STEEL)
        # prisma: encostado na fenda, com o canto externo chanfrado
        d.polygon([(X(0.335) * lado, prisma_y0 * lado),
                   (X(0.5 - fenda_c / 2) * lado, prisma_y0 * lado),
                   (X(0.5 - fenda_c / 2) * lado, (corpo_y0 + 0.04) * lado),
                   (X(0.235) * lado, (corpo_y0 + 0.04) * lado)],
                  fill=STEEL)

        # ------------------------------------------------------ a pena
        # base no alto e fora, ponta apontando pra dentro e pra baixo
        corpo_pena, fenda_pena = _pena(0.132, 0.225, corte=detalhe)
        ang = -sinal * 30
        base_x, base_y = X(0.268), 0.462
        d.polygon(_situar(corpo_pena, ang, base_x, base_y, lado), fill=CREME)
        if fenda_pena:
            d.polygon(_situar(fenda_pena, ang, base_x, base_y, lado), fill=STEEL)

    # ------------------------------------------------------------ lente
    r_ext, r_int = 0.070, 0.040
    d.ellipse(R(0.5 - r_ext, 0.5 - r_ext, 0.5 + r_ext, 0.5 + r_ext), fill=PEACH)
    d.ellipse(R(0.5 - r_int, 0.5 - r_int, 0.5 + r_int, 0.5 + r_int), fill=CREME)

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
