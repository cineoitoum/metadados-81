"""
Gera o ícone do app em pixel art, em .icns (macOS) e .ico (Windows).

    python packaging/make_icon.py

São DOIS desenhos, não um. O aspecto pixelado vem da razão entre a
grade e o tamanho de saída, e a grade precisa dividir o tamanho por
inteiro — senão a ampliação borra. Como nenhuma grade única divide bem
16 e 512 ao mesmo tempo, cada faixa de tamanho tem o seu desenho, que
é como os ícones clássicos de Mac e Windows sempre foram feitos:

    MAPA16  ->  16, 32, 48      (menu, lista do Finder, barra de tarefas)
    MAPA64  ->  64 a 1024       (Dock, Finder em ícones, tela cheia)

Cada caractere dos mapas é um pixel, e a ampliação usa NEAREST: nenhuma
borda embaçada, nenhum meio-pixel. O fundo é transparente.

Pra mexer no desenho basta trocar caracteres. A legenda está em CORES.

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
    ".": (0, 0, 0, 0),            # vazio (fundo transparente)
    "K": (26, 40, 46, 255),       # contorno
    "T": (138, 162, 168, 255),    # chapa de cima, luz
    "t": (108, 132, 139, 255),    # chapa de cima, meio-tom
    "u": (84, 106, 113, 255),     # chapa de cima, sombra
    "S": (63, 90, 98, 255),       # corpo
    "h": (80, 108, 116, 255),     # corpo, luz
    "s": (48, 70, 77, 255),       # corpo, sombra
    "B": (44, 65, 73, 255),       # barril da lente
    "b": (62, 86, 94, 255),       # barril, luz
    "P": (254, 130, 84, 255),     # aro da lente, peach
    "p": (226, 98, 54, 255),      # peach escurecido
    "D": (22, 35, 41, 255),       # vidro
    "d": (34, 52, 60, 255),       # vidro, borda
    "W": (168, 198, 205, 255),    # reflexo no vidro
}

# Versão mínima: só o que sobrevive a 16 pixels de lado.
MAPA16 = [
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

# Versão detalhada: prisma, seletor, disparador, pega texturada, barril
# serrilhado e reflexo no vidro.
MAPA64 = [
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "......................KKKKKKKKKKKKKK............................",
    ".....................tttttttttttttttt...........................",
    "....................KtTTTTTTTTTTTTTTtK..........................",
    ".........KKKKKKKKK..KtTTTTTTTTTTTTTTtK.......KKKKKKKKKK.........",
    "........KuuuuuuuuuK.KtTTTTTTTTTTTTTTtK......KppppppppppK........",
    "........KutttttttuK.KtTTTTTTTTTTTTTTtK......KpPPPPPPPPpK........",
    "........KutttttttuK.KtuuuuuuuuuuuuuutK......KpPPPPPPPPpK........",
    "........KuuuuuuuuuK.KtuuuuuuuuuuuuuutK......KpPPPPPPPPpK........",
    "........KuuuuuuuuuK..tuuuuuuuuuuuuuut.......KppppppppppK........",
    ".....KKKKuuuuuuuuuKKKttttttttttttttttKKKKKKKKppppppppppKKKK.....",
    "....TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT....",
    "...TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT...",
    "..KTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTK..",
    "..KuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuK..",
    "..KuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuK..",
    "..KuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuK..",
    "..KSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSK..",
    "..KhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhK..",
    "..KhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhK..",
    "..KSSSSSSSSSSSSSSSSSSSSSSSSKKKKSSSSSSSSSSSSSSSSSSSSKKKKKKKKSSK..",
    "..KSSSSSSSSSSSSSSSSSSSSKKKKbbbbKKKKSSSSSSSSSSSSSSShhhhhhhhhhSK..",
    "..KSSSSSSSSSSSSSSSSSSKKKbbbBKBBbbbKKKSSSSSSSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSSSSSSKKbbBKBBKBBBKBbbKKSSSSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSSSSKbbBKBBKppppKBBKBbbKSSSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSSSKbbBBKpppPPPPpppKBBbbKSSSSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSSSKKbKKBpPPPPPPPPPPpBKKbKKSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSSKbBBBpPPPPddddPPPPpBBBbKSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSKbKBBpPPPddDDDDddPPPpBBKbKSSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSSKbBKpPPPdDWDDDDDDdPPPpKBbKSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSKbbBBpPPdDWWWDDDDDDdPPpBBbbKSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSKbKKpPPdDWWWDDDDDDDDdPPpKKbKSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSKbBBpPPdDWWDDDDDDDDDdPPpBBbKSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSKbBBpPPdDWDDDDDDDDDDdPPpBBbKSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSKbKKpPPdDDDDDDDDDDDDdPPpKKbKSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSKbBBpPPdDDDDDDDDDDDDdPPpBBbKSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSKbBBpPPdDDDDDDDDDDDDdPPpBBbKSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSKbKKpPPdDDDDDDDDDDDDdPPpKKbKSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSKbbBBpPPdDDDDDDDDDDdPPpBBbbKSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSKbBKpPPPdDDDDDDDDdPPPpKBbKSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSKbKBBpPPPddDDDDddPPPpBBKbKSSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSSSKbBBBpPPPPddddPPPPpBBBbKSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSSKKbKKBpPPPPPPPPPPpBKKbKKSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSSSKbbBBKpppPPPPpppKBBbbKSSSSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSSSSSKbbBKBBKppppKBBKBbbKSSSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSSSSSKKbbBKBBBKBBKBbbKKSSSSSSSSSSSKhhhhhhhhhhKK..",
    "..KSSSSSSSSSSSSSSSSSSKKKbbbBBKBbbbKKKSSSSSSSSSSSSKhsssssssshKK..",
    "..KSSSSSSSSSSSSSSSSSSSSKKKKbbbbKKKKSSSSSSSSSSSSSSKhhhhhhhhhhKK..",
    "..KssssssssssssssssssssssssKKKKssssssssssssssssssShhhhhhhhhhSK..",
    "..KssssssssssssssssssssssssssssssssssssssssssssssSSKKKKKKKKSSK..",
    "...ssssssssssssssssssssssssssssssssssssssssssssssssssssssssss...",
    "....ssssssssssssssssssssssssssssssssssssssssssssssssssssssss....",
    ".....KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK.....",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
]


def _grade(mapa):
    lado = len(mapa)
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    px = img.load()
    for y, linha in enumerate(mapa):
        if len(linha) != lado:
            raise ValueError("linha %d tem %d colunas, esperava %d"
                             % (y, len(linha), lado))
        for x, ch in enumerate(linha):
            px[x, y] = CORES[ch]
    return img


def desenhar(tamanho: int) -> Image.Image:
    """Escolhe o desenho cuja grade divide o tamanho por inteiro,
    preferindo sempre o mais detalhado que couber."""
    for mapa in (MAPA64, MAPA16):
        lado = len(mapa)
        if tamanho >= lado and tamanho % lado == 0:
            return _grade(mapa).resize((tamanho, tamanho), Image.NEAREST)
    # nenhum sistema pede um tamanho assim; fica o mínimo, sem borrar
    return _grade(MAPA16).resize((tamanho, tamanho), Image.NEAREST)


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
