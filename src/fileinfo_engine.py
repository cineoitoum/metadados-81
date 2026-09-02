"""
Ficha técnica da imagem — tudo o que o arquivo sabe sobre si.

Lê num único chamado do ExifTool e devolve agrupado por assunto, pronto
pra exibir. Só entra na lista o que EXISTE no arquivo: linha vazia num
painel técnico é ruído, e faz parecer que o dado sumiu quando na verdade
nunca esteve lá.

Sobre a qualidade JPEG: ela NÃO é gravada no arquivo. O que fica gravado
são as tabelas de quantização, e a qualidade é estimada comparando-as
com as tabelas padrão do IJG — o mesmo caminho que o ImageMagick usa.
Por isso o valor sai marcado como aproximado; para JPEG escrito por
libjpeg (a maioria) o acerto é bom, para outros codificadores é um
palpite informado.
"""

import json
import os
import subprocess
from datetime import datetime
from typing import List, Optional, Tuple

import platform_utils

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# tags pedidas ao ExifTool, agrupadas pela seção em que aparecem
_TAGS = [
    "FileName", "FileType", "FileSize", "FileModifyDate", "MIMEType",
    "ImageWidth", "ImageHeight", "Megapixels", "BitsPerSample",
    "ColorComponents", "ColorSpace", "ProfileDescription", "Orientation",
    "XResolution", "YResolution", "ResolutionUnit",
    "EncodingProcess", "YCbCrSubSampling",
    "Make", "Model", "LensModel", "LensID", "SerialNumber", "Software",
    "DateTimeOriginal", "CreateDate",
    "ISO", "FNumber", "ExposureTime", "ShutterSpeed", "FocalLength",
    "FocalLengthIn35mmFormat", "ExposureCompensation", "ExposureProgram",
    "MeteringMode", "Flash", "WhiteBalance",
    "GPSPosition", "GPSAltitude",
]


def _run(path: str) -> dict:
    try:
        import metadata_engine
        binario = metadata_engine._find_exiftool()
    except Exception:
        binario = None
    if not binario:
        return {}
    comando = platform_utils.exiftool_command(binario) + ["-json", "-a", "-G0:1"]
    comando += ["-" + t for t in _TAGS]
    comando.append(path)
    try:
        saida = subprocess.run(comando, capture_output=True, text=True,
                               encoding="utf-8", timeout=60,
                               **platform_utils.subprocess_flags())
        if saida.returncode != 0:
            return {}
        dados = json.loads(saida.stdout)[0]
    except Exception:
        return {}
    # as chaves vêm como "Grupo:Tag"; achata pro nome simples, que é o
    # que interessa aqui, mantendo a primeira ocorrência
    plano = {}
    for chave, valor in dados.items():
        simples = chave.split(":")[-1]
        plano.setdefault(simples, valor)
    return plano


# ------------------------------------------------------- qualidade JPEG

# tabelas de quantização padrão do IJG, para qualidade 50
_IJG_LUMA = [
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
]


def _scale_for(qualidade: int) -> float:
    """Fator de escala do IJG para uma dada qualidade."""
    q = max(1, min(100, qualidade))
    return (5000.0 / q) if q < 50 else (200.0 - q * 2)


def estimate_jpeg_quality(path: str) -> Optional[int]:
    """Estima a qualidade comparando a tabela de luminância do arquivo
    com a tabela IJG reescalada para cada qualidade de 1 a 100, e
    devolvendo a que menos diverge.

    Devolve None quando não dá pra saber — arquivo não-JPEG, sem tabela,
    ou Pillow ausente. Nesses casos é melhor não mostrar nada do que
    mostrar um número inventado."""
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as im:
            if im.format != "JPEG":
                return None
            tabelas = getattr(im, "quantization", None)
            if not tabelas or 0 not in tabelas:
                return None
            tabela = list(tabelas[0])[:64]
    except Exception:
        return None
    if len(tabela) < 64:
        return None

    melhor, menor_erro = None, None
    for q in range(1, 101):
        escala = _scale_for(q)
        erro = 0.0
        for base, real in zip(_IJG_LUMA, tabela):
            esperado = int((base * escala + 50) / 100)
            esperado = max(1, min(255, esperado))
            erro += abs(esperado - real)
        if menor_erro is None or erro < menor_erro:
            menor_erro, melhor = erro, q
    return melhor


# ------------------------------------------------------------- formatação

def _tamanho_legivel(path: str) -> str:
    try:
        bytes_ = os.path.getsize(path)
    except OSError:
        return ""
    for unidade in ("bytes", "KB", "MB", "GB"):
        if bytes_ < 1024 or unidade == "GB":
            if unidade == "bytes":
                return "%d bytes" % bytes_
            return "%.1f %s" % (bytes_, unidade)
        bytes_ /= 1024.0
    return ""


def _bits(valor) -> str:
    """BitsPerSample vem com um valor por canal ("8 8 8"). Quando todos
    são iguais — o caso normal — mostra um só."""
    if valor in (None, ""):
        return ""
    partes = str(valor).replace(",", " ").split()
    if not partes:
        return ""
    if len(set(partes)) == 1:
        return "%s bits/canal" % partes[0]
    return "%s bits" % " / ".join(partes)


def _proporcao(largura, altura) -> str:
    """Proporção reduzida — 6000x4000 vira 3:2."""
    try:
        largura, altura = int(largura), int(altura)
    except (TypeError, ValueError):
        return ""
    if largura <= 0 or altura <= 0:
        return ""
    from math import gcd
    d = gcd(largura, altura)
    a, b = largura // d, altura // d
    # proporções feias (17:11) não ajudam ninguém; aproxima pras comuns
    if a > 20 or b > 20:
        alvo = largura / float(altura)
        comuns = [(1, 1), (5, 4), (4, 3), (3, 2), (16, 10), (16, 9), (2, 1),
                  (21, 9), (4, 5), (3, 4), (2, 3), (9, 16)]
        a, b = min(comuns, key=lambda p: abs(p[0] / float(p[1]) - alvo))
        return "≈ %d:%d" % (a, b)
    return "%d:%d" % (a, b)


def _data_legivel(valor) -> str:
    if not valor:
        return ""
    texto = str(valor).strip()
    for formato in ("%Y:%m:%d %H:%M:%S%z", "%Y:%m:%d %H:%M:%S", "%Y:%m:%d"):
        try:
            return datetime.strptime(texto[:25] if "%z" in formato else texto[:19],
                                     formato).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue
    return texto


def describe(path: str) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """A ficha inteira: [(seção, [(rótulo, valor), ...]), ...].

    Seções e linhas sem conteúdo são omitidas."""
    if not path or not os.path.isfile(path):
        return []
    d = _run(path)

    largura = d.get("ImageWidth")
    altura = d.get("ImageHeight")

    resolucao = ""
    if d.get("XResolution"):
        unidade = str(d.get("ResolutionUnit", "")).lower()
        sufixo = "dpi" if "inch" in unidade or unidade in ("2", "") else str(d.get("ResolutionUnit"))
        resolucao = "%s %s" % (d.get("XResolution"), sufixo)

    qualidade = estimate_jpeg_quality(path)

    secoes = [
        ("Arquivo", [
            ("Nome", d.get("FileName") or os.path.basename(path)),
            ("Formato", d.get("FileType", "")),
            ("Tamanho", _tamanho_legivel(path)),
            ("Modificado", _data_legivel(d.get("FileModifyDate"))),
        ]),
        ("Imagem", [
            ("Dimensões", "%s × %s px" % (largura, altura) if largura and altura else ""),
            ("Megapixels", "%s MP" % d.get("Megapixels") if d.get("Megapixels") else ""),
            ("Proporção", _proporcao(largura, altura)),
            ("Resolução", resolucao),
            ("Profundidade", _bits(d.get("BitsPerSample"))),
            ("Canais", str(d.get("ColorComponents", "")) if d.get("ColorComponents") else ""),
            ("Espaço de cor", d.get("ColorSpace", "")),
            ("Perfil ICC", d.get("ProfileDescription", "")),
            ("Orientação", d.get("Orientation", "")),
        ]),
        ("Compressão", [
            ("Processo", d.get("EncodingProcess", "")),
            ("Subamostragem", d.get("YCbCrSubSampling", "")),
            ("Qualidade", "≈ %d (estimada)" % qualidade if qualidade else ""),
        ]),
        ("Câmera", [
            ("Marca", d.get("Make", "")),
            ("Modelo", d.get("Model", "")),
            ("Lente", d.get("LensModel") or d.get("LensID", "")),
            ("Nº de série", d.get("SerialNumber", "")),
            ("Software", d.get("Software", "")),
        ]),
        ("Captura", [
            ("Data", _data_legivel(d.get("DateTimeOriginal") or d.get("CreateDate"))),
            ("ISO", str(d.get("ISO", "")) if d.get("ISO") else ""),
            ("Abertura", "f/%s" % d.get("FNumber") if d.get("FNumber") else ""),
            ("Velocidade", "%s s" % (d.get("ShutterSpeed") or d.get("ExposureTime"))
             if (d.get("ShutterSpeed") or d.get("ExposureTime")) else ""),
            ("Distância focal", d.get("FocalLength", "")),
            ("Equiv. 35mm", d.get("FocalLengthIn35mmFormat", "")),
            ("Compensação", str(d.get("ExposureCompensation", ""))
             if d.get("ExposureCompensation") not in (None, "", 0) else ""),
            ("Programa", d.get("ExposureProgram", "")),
            ("Medição", d.get("MeteringMode", "")),
            ("Flash", d.get("Flash", "")),
            ("Balanço de branco", d.get("WhiteBalance", "")),
        ]),
        ("Local", [
            ("GPS", d.get("GPSPosition", "")),
            ("Altitude", d.get("GPSAltitude", "")),
        ]),
    ]

    resultado = []
    for titulo, linhas in secoes:
        preenchidas = [(r, str(v).strip()) for r, v in linhas if v not in (None, "")]
        if preenchidas:
            resultado.append((titulo, preenchidas))
    return resultado
