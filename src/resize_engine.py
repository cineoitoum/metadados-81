"""
Redimensionamento de imagem, preservando os metadados.

ATENÇÃO — este é o único módulo do app que REESCREVE PIXELS.

Todo o resto trabalha só nos blocos de metadado (APP1/IPTC/XMP) e deixa a
imagem byte a byte idêntica. Redimensionar quebra isso por definição: o
JPEG é recodificado, e recodificar perde qualidade, sempre. Por isso:

  - o padrão é gravar uma CÓPIA, nunca sobrescrever o original;
  - sobrescrever exige pedir explicitamente;
  - a qualidade do JPEG é escolhida por quem usa, com 92 como padrão —
    alto o bastante para não aparecer artefato em tela cheia.

E há uma armadilha que este módulo existe pra resolver: o Pillow DESCARTA
todos os metadados ao salvar. Uma foto redimensionada com Pillow puro sai
sem legenda, sem autor, sem direitos. Aqui os metadados são copiados de
volta do original com o ExifTool, depois do salvamento.
"""

import os
from pathlib import Path
from typing import Optional, Tuple

import platform_utils

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# sufixo do arquivo gerado quando não se sobrescreve
DEFAULT_SUFFIX = "_redim"

DEFAULT_QUALITY = 92


class ResizeError(RuntimeError):
    pass


def get_size(path: str) -> Optional[Tuple[int, int]]:
    """(largura, altura) da imagem, ou None se não der pra ler."""
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def fit_size(largura_original: int, altura_original: int,
             largura: Optional[int], altura: Optional[int],
             manter_proporcao: bool = True) -> Tuple[int, int]:
    """Calcula o tamanho final.

    Com o cadeado FECHADO (manter_proporcao), o lado informado manda e o
    outro é derivado. Se os dois forem informados, a imagem é encaixada
    DENTRO da caixa — nunca estica, nunca corta.

    Com o cadeado aberto, os dois valores valem como digitados, e a
    imagem distorce. É escolha de quem usa.
    """
    if largura_original <= 0 or altura_original <= 0:
        raise ResizeError("Tamanho original inválido.")

    proporcao = largura_original / float(altura_original)

    if not manter_proporcao:
        nova_l = int(largura or largura_original)
        nova_a = int(altura or altura_original)
        return max(1, nova_l), max(1, nova_a)

    if largura and altura:
        # encaixa na caixa, preservando a proporção
        escala = min(largura / float(largura_original),
                     altura / float(altura_original))
        return (max(1, int(round(largura_original * escala))),
                max(1, int(round(altura_original * escala))))
    if largura:
        return max(1, int(largura)), max(1, int(round(largura / proporcao)))
    if altura:
        return max(1, int(round(altura * proporcao))), max(1, int(altura))
    return largura_original, altura_original


def suggest_output(path: str, sufixo: str = DEFAULT_SUFFIX) -> str:
    raiz, extensao = os.path.splitext(path)
    return raiz + sufixo + extensao


def resize(path: str, largura: Optional[int] = None, altura: Optional[int] = None,
           manter_proporcao: bool = True, destino: Optional[str] = None,
           qualidade: int = DEFAULT_QUALITY,
           sobrescrever: bool = False) -> dict:
    """Redimensiona e devolve o que aconteceu.

    Sem `destino` e sem `sobrescrever`, grava ao lado do original com o
    sufixo _redim. Sobrescrever o original é possível, mas precisa ser
    pedido — recodificar por cima do arquivo bom é irreversível.
    """
    if not PIL_AVAILABLE:
        raise ResizeError("Pillow não está instalado — não consigo redimensionar.")
    if not os.path.isfile(path):
        raise ResizeError("Arquivo não encontrado: %s" % path)

    original = get_size(path)
    if original is None:
        raise ResizeError("Não consegui ler as dimensões da imagem.")
    largura_original, altura_original = original

    nova_l, nova_a = fit_size(largura_original, altura_original,
                              largura, altura, manter_proporcao)

    if (nova_l, nova_a) == (largura_original, altura_original):
        return {"mudou": False, "destino": path,
                "de": original, "para": (nova_l, nova_a),
                "aviso": "O tamanho pedido é igual ao original — nada foi gravado."}

    if sobrescrever:
        saida = path
    else:
        saida = destino or suggest_output(path)

    try:
        with Image.open(path) as im:
            # converte modo que o JPEG não aceita, mas só quando precisa
            extensao = os.path.splitext(saida)[1].lower()
            if extensao in (".jpg", ".jpeg") and im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            # LANCZOS é o reamostrador de melhor qualidade do Pillow para
            # reduzir; a diferença aparece em textura fina e texto
            redimensionada = im.resize((nova_l, nova_a), Image.LANCZOS)

            # O formato precisa ser EXPLÍCITO: o Pillow o deduz da
            # extensão, e o arquivo é gravado como .tmp antes de assumir
            # o nome final — sem isto ele não sabe o que escrever.
            formatos = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                        ".tif": "TIFF", ".tiff": "TIFF"}
            formato = formatos.get(extensao, "JPEG")

            parametros = {"format": formato}
            if formato == "JPEG":
                parametros.update({"quality": int(qualidade), "subsampling": 0,
                                   "optimize": True, "progressive": True})
            elif formato == "TIFF":
                parametros["compression"] = "tiff_lzw"

            Path(os.path.dirname(saida) or ".").mkdir(parents=True, exist_ok=True)
            temporario = saida + ".tmp"
            redimensionada.save(temporario, **parametros)
    except OSError as e:
        raise ResizeError("Não consegui redimensionar: %s" % e)

    # O Pillow descartou TODOS os metadados ao salvar. Traz de volta do
    # original — sem isto a foto redimensionada sai sem legenda, sem
    # autor e sem direitos, o que é o oposto do que este app faz.
    aviso = _copy_metadata(path, temporario)

    try:
        os.replace(temporario, saida)
    except OSError as e:
        raise ResizeError("Não consegui gravar o arquivo final: %s" % e)

    return {"mudou": True, "destino": saida, "de": original,
            "para": (nova_l, nova_a), "aviso": aviso}


def _copy_metadata(origem: str, destino: str) -> str:
    """Copia todas as tags do original para o arquivo novo.

    Devolve string vazia se deu certo, ou um aviso legível se não —
    porque uma foto redimensionada sem metadado ainda é útil, mas o
    usuário precisa saber."""
    import subprocess
    try:
        import metadata_engine
        binario = metadata_engine._find_exiftool()
    except Exception:
        binario = None
    if not binario:
        return ("Redimensionei, mas não achei o ExifTool para copiar os "
                "metadados — o arquivo novo está sem eles.")
    try:
        comando = platform_utils.exiftool_command(binario) + [
            "-tagsFromFile", origem,
            "-all:all",
            # a dimensão tem de ser a NOVA, não a copiada do original
            "-XResolution", "-YResolution", "-ResolutionUnit",
            "--Orientation",
            "-overwrite_original",
            destino,
        ]
        resultado = subprocess.run(comando, capture_output=True, text=True,
                                   timeout=120, **platform_utils.subprocess_flags())
        if resultado.returncode != 0:
            return ("Redimensionei, mas o ExifTool falhou ao copiar os "
                    "metadados: %s" % (resultado.stderr.strip()[:160]))
    except Exception as e:
        return "Redimensionei, mas não consegui copiar os metadados: %s" % e
    return ""
