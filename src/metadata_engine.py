"""
Motor de leitura, validação e escrita de metadados IPTC/XMP para fotos.

Depende do ExifTool (https://exiftool.org). No app empacotado, o ExifTool
vai embutido no bundle (veja _bundled_exiftool_path) — não depende de nada
instalado à parte. Não usa nenhuma biblioteca que reprocesse/recomprima
pixels — o ExifTool escreve apenas os blocos de metadado (APP1/IPTC/XMP),
a imagem em si permanece byte a byte idêntica.
"""

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

import platform_utils


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}

# --------------------------------------------- vocabulários de agência

# Origem digital (IPTC DigitalSourceType). Deixou de ser opcional:
# Adobe Stock, Getty e Shutterstock exigem declarar se a imagem foi
# gerada ou alterada por IA, e envio sem isso é recusado ou removido.
# O valor gravado é a IRI do vocabulário oficial do IPTC; o rótulo é só
# o que aparece na tela.
DIGITAL_SOURCE_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
DIGITAL_SOURCES = [
    ("", "— não declarado —"),
    (DIGITAL_SOURCE_BASE + "digitalCapture", "Foto de câmera digital"),
    (DIGITAL_SOURCE_BASE + "negativeFilm", "Filme negativo digitalizado"),
    (DIGITAL_SOURCE_BASE + "positiveFilm", "Slide/positivo digitalizado"),
    (DIGITAL_SOURCE_BASE + "print", "Impresso digitalizado"),
    (DIGITAL_SOURCE_BASE + "minorHumanEdits", "Foto com edições menores"),
    (DIGITAL_SOURCE_BASE + "compositeCapture", "Composição de fotos reais"),
    (DIGITAL_SOURCE_BASE + "algorithmicallyEnhanced", "Foto melhorada por algoritmo"),
    (DIGITAL_SOURCE_BASE + "compositeWithTrainedAlgorithmicMedia",
     "Foto real com elementos gerados por IA"),
    (DIGITAL_SOURCE_BASE + "trainedAlgorithmicMedia", "Gerada por IA"),
]

# Liberação de modelo e de propriedade (vocabulário PLUS). Foto com
# pessoa reconhecível ou propriedade privada sem status marcado é
# recusada pelas agências.
RELEASE_STATUSES = [
    ("", "— não declarado —"),
    ("Not Applicable", "Não se aplica"),
    ("Unlimited Model Releases", "Liberação total"),
    ("Limited or Incomplete Model Releases", "Liberação parcial"),
    ("None", "Sem liberação"),
]

PROPERTY_RELEASE_STATUSES = [
    ("", "— não declarado —"),
    ("Not Applicable", "Não se aplica"),
    ("Unlimited Property Releases", "Liberação total"),
    ("Limited or Incomplete Property Releases", "Liberação parcial"),
    ("None", "Sem liberação"),
]

# Limites de palavra-chave das agências. Passar disso trunca ou reprova
# o envio — melhor avisar na tela que descobrir na rejeição.
KEYWORD_LIMITS = {"Adobe Stock": 49, "Shutterstock": 50, "Getty": 50}
KEYWORD_SOFT_LIMIT = 49

# --------------------------------------------------------------- ExifTool

def _bundled_exiftool_path() -> Optional[str]:
    """No app empacotado (PyInstaller), o ExifTool vai junto dentro do
    bundle — quem recebe o app não precisa instalar nada.

    O nome do executável muda por sistema: no macOS o ExifTool é um script
    Perl que roda com o Perl do sistema (presente de fábrica); no Windows
    não existe Perl de sistema, e a distribuição oficial é um .exe
    autocontido. platform_utils sabe qual esperar."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    candidate = os.path.join(base, "exiftool_bundle", platform_utils.exiftool_bundle_name())
    return candidate if os.path.isfile(candidate) else None


def _find_exiftool() -> Optional[str]:
    bundled = _bundled_exiftool_path()
    if bundled:
        return bundled
    # Apps abertos pelo Finder/Launchpad herdam o PATH restrito do launchd
    # (sem /usr/local/bin nem /opt/homebrew/bin), então shutil.which sozinho
    # falha mesmo com o ExifTool instalado via Homebrew/instalador oficial.
    found = shutil.which("exiftool")
    if found:
        return found
    for candidate in platform_utils.exiftool_fallback_paths():
        # basta EXISTIR: exiftool_command() decide se chama direto ou
        # via perl. Exigir X_OK aqui rejeitaria um script Perl valido que
        # so perdeu o bit ao ser copiado.
        if os.path.isfile(candidate):
            return candidate
    return None


class ExifToolNotFound(RuntimeError):
    pass


class MetadataWriteError(RuntimeError):
    pass


def check_exiftool() -> bool:
    return _find_exiftool() is not None


def _run_exiftool(args: List[str]) -> str:
    exiftool_bin = _find_exiftool()
    if not exiftool_bin:
        raise ExifToolNotFound(platform_utils.exiftool_install_hint())
    # nao assume que o binario tem bit de execucao: em macOS/Linux o
    # ExifTool e um script Perl e volumes de nuvem descartam o bit
    comando = platform_utils.exiftool_command(exiftool_bin)
    result = subprocess.run(
        comando + args, capture_output=True, text=True, encoding="utf-8",
        **platform_utils.subprocess_flags()
    )
    if result.returncode != 0:
        raise MetadataWriteError(result.stderr.strip() or "Erro desconhecido do ExifTool.")
    return result.stdout


# ------------------------------------------------------------- PhotoFields

@dataclass
class PhotoFields:
    caption: str = ""
    headline: str = ""
    instructions: str = ""
    keywords: List[str] = field(default_factory=list)
    creator: str = ""
    creator_url: str = ""
    sublocation: str = ""   # o lugar dentro da cidade: praia, teatro, bairro
    city: str = ""
    state: str = ""
    country: str = ""
    country_code: str = ""  # ISO 3166-1 alfa-2/3, exigido por banco de imagens
    copyright: str = ""
    credit: str = ""
    source: str = ""
    usage_terms: str = ""

    # --- exigências de banco de imagens ---
    object_name: str = ""          # título curto de venda (≠ headline)
    alt_text: str = ""             # texto alternativo de acessibilidade
    extended_description: str = ""  # descrição longa de acessibilidade
    digital_source: str = ""       # IRI da origem digital (declaração de IA)
    model_release: str = ""        # status PLUS de liberação de modelo
    property_release: str = ""     # status PLUS de liberação de propriedade
    # Vem do EXIF da câmera, mas passa a ser EDITÁVEL: câmera com data
    # errada, foto escaneada e material de arquivo são casos reais em que
    # a data da captura precisa ser corrigida à mão.
    date_created: Optional[datetime] = None

    def keywords_as_text(self) -> str:
        """Exibe separado por vírgula — é como se digita naturalmente e
        como banco de imagem costuma pedir."""
        return ", ".join(self.keywords)

    @staticmethod
    def keywords_from_text(text: str) -> List[str]:
        """Aceita vírgula E ponto e vírgula como separador.

        A vírgula é o gesto natural e o padrão dos bancos de imagem; o
        ponto e vírgula era o separador das versões anteriores e continua
        valendo, pra não quebrar quem já tem o hábito ou colou de um
        arquivo antigo.

        Duplicatas são removidas preservando a ordem: em banco de imagem
        a ordem das palavras-chave é sinal de relevância, então a primeira
        ocorrência é a que vale."""
        bruto = (text or "").replace(";", ",")
        vistos = set()
        saida = []
        for parte in bruto.split(","):
            limpo = parte.strip()
            if not limpo:
                continue
            chave = limpo.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            saida.append(limpo)
        return saida


# Mapa central: chave de campo -> tags de metadado escritas com o mesmo
# valor. Usado tanto pela gravação de uma foto só (todas as chaves) quanto
# pelo lote (só as chaves marcadas pelo usuário como "aplicar a todas").
SCALAR_FIELD_TAGS: Dict[str, List[str]] = {
    "caption": ["IPTC:Caption-Abstract", "XMP-dc:Description", "EXIF:ImageDescription"],
    "headline": ["IPTC:Headline", "XMP-photoshop:Headline"],
    "instructions": ["IPTC:SpecialInstructions", "XMP-photoshop:Instructions"],
    "creator": ["IPTC:By-line", "XMP-dc:Creator", "EXIF:Artist"],
    "creator_url": ["XMP-iptcCore:CreatorWorkURL"],
    # Sub-location e o lugar ESPECIFICO dentro da cidade ("Praia de
    # Copacabana", "Teatro Municipal"). Bancos de imagem usam pra busca
    # geografica fina, abaixo do nivel de cidade.
    "sublocation": ["IPTC:Sub-location", "XMP-iptcCore:Location"],
    "city": ["IPTC:City", "XMP-photoshop:City"],
    "state": ["IPTC:Province-State", "XMP-photoshop:State"],
    "country": ["IPTC:Country-PrimaryLocationName", "XMP-photoshop:Country"],
    # codigo ISO do pais — varias agencias rejeitam o envio sem ele
    "country_code": ["IPTC:Country-PrimaryLocationCode", "XMP-iptcCore:CountryCode"],
    "copyright": ["IPTC:CopyrightNotice", "XMP-dc:Rights"],
    "credit": ["IPTC:Credit"],
    "source": ["IPTC:Source"],
    "usage_terms": ["XMP-xmpRights:UsageTerms"],
    # título curto de venda. Várias agências usam ObjectName, e não o
    # Headline, como o título que aparece na busca.
    "object_name": ["IPTC:ObjectName", "XMP-dc:Title"],
    # ATENÇÃO ao grupo: as tags de acessibilidade vivem em
    # XMP-iptcCore, NÃO em XMP-iptcExt. Escrevê-las no grupo errado
    # falha em silêncio — o ExifTool avisa e não grava nada.
    "alt_text": ["XMP-iptcCore:AltTextAccessibility"],
    "extended_description": ["XMP-iptcCore:ExtDescrAccessibility"],
    "digital_source": ["XMP-iptcExt:DigitalSourceType"],
    "model_release": ["XMP-plus:ModelReleaseStatus"],
    "property_release": ["XMP-plus:PropertyReleaseStatus"],
}
KEYWORDS_TAGS = ["IPTC:Keywords", "XMP-dc:Subject"]
ALL_FIELD_KEYS = list(SCALAR_FIELD_TAGS.keys()) + ["keywords"]

# Campos avançados/personalizados: além do padrãozinho fixo acima, o
# usuário pode gravar QUALQUER tag do ExifTool (ex.: "XMP:Rating",
# "IPTC:Urgency", "IPTC:ObjectName") digitando o nome dela. Só uma
# validação leve de formato — o ExifTool é quem valida se a tag existe.
_TAG_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*(:[A-Za-z][A-Za-z0-9_\-]*)?$")


def is_valid_tag_name(name: str) -> bool:
    return bool(_TAG_NAME_RE.match((name or "").strip()))

FIELD_LABELS: Dict[str, str] = {
    "caption": "Legenda/Descrição",
    "headline": "Título (Headline)",
    "instructions": "Descrição ampliada",
    "keywords": "Palavras-chave",
    "creator": "Criador",
    "creator_url": "Site/contato do criador",
    "sublocation": "Local (dentro da cidade)",
    "city": "Cidade",
    "state": "Estado/Província",
    "country": "País",
    "country_code": "Código do país (ISO)",
    "copyright": "Copyright",
    "credit": "Crédito",
    "source": "Fonte",
    "usage_terms": "Termos de uso/Licença",
    "object_name": "Título de venda",
    "alt_text": "Texto alternativo (acessibilidade)",
    "extended_description": "Descrição estendida (acessibilidade)",
    "digital_source": "Origem digital / declaração de IA",
    "model_release": "Liberação de modelo",
    "property_release": "Liberação de propriedade",
}

# Campos que fazem sentido repetir automaticamente entre fotos de um mesmo
# lote (mesmo local/autor/condições) — os demais (texto único por foto)
# começam desmarcados por padrão na tela de lote.
BATCH_DEFAULT_CHECKED = {
    "keywords", "creator", "creator_url", "sublocation", "city", "state",
    "country", "country_code", "digital_source", "model_release",
    "property_release",
    "copyright", "credit", "source", "usage_terms",
}


# ----------------------------------------------------- Perfis de validação

VALIDATION_PROFILES: Dict[str, dict] = {
    "padrao": {
        "label": "Perfil padrão",
        "caption_max_len": 100,
        "forbidden_chars": ['"', "'", ",", "(", ")"],
        "min_edge": 4000,
        "required": {"caption", "keywords", "creator", "city", "state", "country"},
    },
    "sem_restricoes": {
        "label": "Sem restrições (uso geral)",
        "caption_max_len": None,
        "forbidden_chars": [],
        "min_edge": None,
        "required": set(),
    },
    # ------------------------------------------------ perfis de agência
    # Cada agência tem suas próprias regras, e descobri-las na rejeição
    # custa tempo. Os limites abaixo são os praticados hoje; se uma
    # agência mudar, é uma linha aqui.
    "adobe_stock": {
        "label": "Adobe Stock",
        "caption_max_len": 200,
        "forbidden_chars": [],
        "min_edge": 1732,          # ~4 MP no lado menor de um 4:3
        "max_keywords": 49,
        "min_keywords": 5,
        "required": {"caption", "keywords", "creator", "digital_source"},
    },
    "shutterstock": {
        "label": "Shutterstock",
        "caption_max_len": 200,
        "forbidden_chars": [],
        "min_edge": 1732,
        "max_keywords": 50,
        "min_keywords": 7,
        "required": {"caption", "keywords", "creator", "digital_source"},
    },
    # PULSAR IMAGENS — regras oficiais de envio do colaborador.
    #
    # Acervo documental e geografico: as fotos sao catalogadas por
    # municipio e estado, e por isso os tres campos de local sao
    # obrigatorios (para fotos fora do Brasil, so Cidade e Pais — o
    # aviso de Estado pode ser ignorado nesse caso).
    #
    # A legenda tem regra dura: 100 caracteres, sem aspas, virgula ou
    # parenteses. E quando ha pessoa com Licenca de Uso de Imagem, a
    # legenda precisa citar "LUI: Nome" com o mesmo nome do arquivo da
    # licenca — nunca codigo numerico.
    "pulsar": {
        "label": "Pulsar Imagens",
        "caption_max_len": 100,
        "forbidden_chars": ['"', "'", ",", "(", ")"],
        "min_edge": 4000,
        "required": {"caption", "keywords", "creator",
                     "city", "state", "country"},
        # --- regras tecnicas, conferidas contra o proprio arquivo ---
        "color_profile": "adobe rgb",
        "color_profile_label": "Adobe RGB",
        "max_iso": 800,
        "max_iso_moderna": 6400,   # Nikon Z / Canon R, quando o tema exigir
        "min_quality": 95,         # qualidade 12 do Photoshop / 100% do Lightroom
        "exige_lui_na_legenda": True,
    },
    "getty": {
        "label": "Getty / iStock",
        "caption_max_len": 250,
        "forbidden_chars": [],
        "min_edge": 2000,
        "max_keywords": 50,
        "min_keywords": 10,
        "required": {"caption", "keywords", "creator", "object_name",
                     "digital_source", "model_release"},
    },
}
DEFAULT_PROFILE = "padrao"


def list_profiles() -> List[tuple]:
    return [(key, cfg["label"]) for key, cfg in VALIDATION_PROFILES.items()]


def profile_value(profile: dict, chave: str, padrao=None):
    """Lê uma regra do perfil sem quebrar nos perfis que não a definem —
    só os de agência têm limite de palavras-chave, por exemplo."""
    return profile.get(chave, padrao)


def get_profile(profile_key: str) -> dict:
    return VALIDATION_PROFILES.get(profile_key, VALIDATION_PROFILES[DEFAULT_PROFILE])


# ------------------------------------------------------------ leitura EXIF

def _parse_exif_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    # formato típico: "2026:06:19 09:24:44" ou com timezone/subsegundos anexados
    core = raw.strip()[:19]
    try:
        return datetime.strptime(core, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def read_existing_fields(path: str) -> PhotoFields:
    """Lê os metadados já existentes no arquivo (para pré-visualização)."""
    out = _run_exiftool(
        [
            "-json",
            "-a",
            "-Caption-Abstract",
            "-IPTC:Headline",
            "-IPTC:SpecialInstructions",
            "-IPTC:By-line",
            "-XMP-iptcCore:CreatorWorkURL",
            "-IPTC:Sub-location",
            "-IPTC:City",
            "-IPTC:Province-State",
            "-IPTC:Country-PrimaryLocationName",
            "-IPTC:Country-PrimaryLocationCode",
            "-IPTC:CopyrightNotice",
            "-IPTC:Credit",
            "-IPTC:Source",
            "-XMP-xmpRights:UsageTerms",
            "-IPTC:ObjectName",
            "-XMP-iptcCore:AltTextAccessibility",
            "-XMP-iptcCore:ExtDescrAccessibility",
            "-XMP-iptcExt:DigitalSourceType",
            "-XMP-plus:ModelReleaseStatus",
            "-XMP-plus:PropertyReleaseStatus",
            "-Keywords",
            "-DateTimeOriginal",
            "-CreateDate",
            # a data IPTC/XMP tem prioridade sobre a da câmera: se alguém
            # já corrigiu a data à mão, é essa que deve voltar pra tela
            "-IPTC:DateCreated",
            "-XMP-photoshop:DateCreated",
            path,
        ]
    )
    data = json.loads(out)[0]

    kw_raw = data.get("Keywords", [])
    if isinstance(kw_raw, str):
        keywords = [kw_raw]
    elif isinstance(kw_raw, list):
        keywords = kw_raw
    else:
        keywords = []

    dt = (_parse_exif_datetime(data.get("XMP:DateCreated") or data.get("DateCreated"))
          or _parse_exif_datetime(data.get("DateTimeOriginal") or data.get("CreateDate")))

    return PhotoFields(
        caption=data.get("Caption-Abstract", "") or "",
        headline=data.get("Headline", "") or "",
        instructions=data.get("SpecialInstructions", "") or "",
        keywords=keywords,
        creator=data.get("By-line", "") or "",
        creator_url=data.get("CreatorWorkURL", "") or "",
        sublocation=data.get("Sub-location", "") or "",
        city=data.get("City", "") or "",
        state=data.get("Province-State", "") or "",
        country=data.get("Country-PrimaryLocationName", "") or "",
        country_code=data.get("Country-PrimaryLocationCode", "") or "",
        copyright=data.get("CopyrightNotice", "") or "",
        credit=data.get("Credit", "") or "",
        source=data.get("Source", "") or "",
        usage_terms=data.get("UsageTerms", "") or "",
        object_name=data.get("ObjectName", "") or "",
        alt_text=data.get("AltTextAccessibility", "") or "",
        extended_description=data.get("ExtDescrAccessibility", "") or "",
        digital_source=data.get("DigitalSourceType", "") or "",
        model_release=data.get("ModelReleaseStatus", "") or "",
        property_release=data.get("PropertyReleaseStatus", "") or "",
        date_created=dt,
    )


def get_camera_datetime(path: str) -> Optional[datetime]:
    out = _run_exiftool(["-json", "-DateTimeOriginal", "-CreateDate", path])
    data = json.loads(out)[0]
    return _parse_exif_datetime(data.get("DateTimeOriginal") or data.get("CreateDate"))


def get_shorter_edge(path: str) -> Optional[int]:
    out = _run_exiftool(["-json", "-ImageWidth", "-ImageHeight", path])
    data = json.loads(out)[0]
    w, h = data.get("ImageWidth"), data.get("ImageHeight")
    if w and h:
        return min(int(w), int(h))
    return None


def get_gps_string(path: str) -> Optional[str]:
    """Coordenadas GPS gravadas pela câmera/celular, só leitura (não é
    editável aqui — mesma lógica da Data: se existe, mostra; não existe,
    mostra que não foi encontrada)."""
    out = _run_exiftool(["-json", "-c", "%+.6f", "-GPSPosition", path])
    data = json.loads(out)[0]
    pos = data.get("GPSPosition")
    return pos or None


# ---------------------------------------------------------------- listagem

def list_image_files(folder: str) -> List[str]:
    """Lista (não recursiva) as fotos suportadas dentro de uma pasta,
    ordenadas por nome."""
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return []
    result = []
    for name in entries:
        if name.startswith("."):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            result.append(os.path.join(folder, name))
    return result


# --------------------------------------------------------------- validação

def validate(fields: PhotoFields, shorter_edge: Optional[int],
             profile_key: str = DEFAULT_PROFILE,
             tecnico: Optional[dict] = None) -> List[str]:
    """Retorna lista de problemas encontrados, de acordo com o perfil de
    validação ativo. Lista vazia = tudo certo.

    `tecnico` traz o que se lê do próprio arquivo e não do formulário —
    ISO, perfil de cor e qualidade de gravação. Só os perfis de agência
    que definem essas regras o usam; os demais ignoram."""
    tecnico = tecnico or {}
    profile = get_profile(profile_key)
    required = profile["required"]
    issues = []
    caption = (fields.caption or "").strip()

    if "caption" in required and not caption:
        issues.append("Legenda/Descrição está vazia.")
    if profile["caption_max_len"] and len(caption) > profile["caption_max_len"]:
        issues.append(f"Legenda tem {len(caption)} caracteres (máximo {profile['caption_max_len']}).")

    found_forbidden = [ch for ch in profile["forbidden_chars"] if ch in caption]
    if found_forbidden:
        issues.append(
            "Legenda contém caractere(s) não permitido(s): " + " ".join(found_forbidden)
        )

    if "keywords" in required and not fields.keywords:
        issues.append("Nenhuma palavra-chave preenchida.")

    # Quantidade de palavras-chave: só os perfis de agência definem
    # limite. Passar do máximo trunca ou reprova o envio; ficar abaixo do
    # mínimo faz a foto quase não aparecer na busca.
    quantas = len(fields.keywords or [])
    maximo = profile_value(profile, "max_keywords")
    minimo = profile_value(profile, "min_keywords")
    if maximo and quantas > maximo:
        issues.append(
            "%d palavras-chave — o perfil aceita no máximo %d. As excedentes "
            "podem ser cortadas no envio." % (quantas, maximo))
    if minimo and 0 < quantas < minimo:
        issues.append(
            "Só %d palavra(s)-chave — o perfil recomenda ao menos %d, senão a "
            "foto quase não aparece na busca." % (quantas, minimo))

    # Campos que as agências passaram a exigir
    # --- regras técnicas, conferidas contra o arquivo ---

    perfil_cor = profile_value(profile, "color_profile")
    if perfil_cor:
        atual = str(tecnico.get("color_profile") or "").lower()
        rotulo_cor = profile_value(profile, "color_profile_label", perfil_cor.upper())
        if not atual:
            issues.append(
                "Não consegui ler o perfil de cor do arquivo — o perfil ativo "
                "exige %s." % rotulo_cor)
        elif perfil_cor not in atual:
            issues.append(
                "Perfil de cor é \"%s\" — o perfil ativo exige %s."
                % (tecnico.get("color_profile"), rotulo_cor))

    teto_iso = profile_value(profile, "max_iso")
    if teto_iso and tecnico.get("iso"):
        try:
            iso = int(float(tecnico["iso"]))
        except (TypeError, ValueError):
            iso = None
        teto_moderno = profile_value(profile, "max_iso_moderna")
        if iso and iso > teto_iso:
            if teto_moderno and iso <= teto_moderno:
                issues.append(
                    "ISO %d acima do teto de %d. Só é aceito até %d em corpos "
                    "recentes (Nikon Z, Canon R) e quando o tema justificar."
                    % (iso, teto_iso, teto_moderno))
            else:
                issues.append("ISO %d acima do máximo de %d aceito pelo perfil."
                              % (iso, teto_iso))

    qualidade_min = profile_value(profile, "min_quality")
    if qualidade_min and tecnico.get("quality"):
        try:
            q = int(tecnico["quality"])
        except (TypeError, ValueError):
            q = None
        if q and q < qualidade_min:
            issues.append(
                "Qualidade de gravação estimada em %d — o perfil pede o "
                "equivalente a 12 no Photoshop ou 100%% no Lightroom." % q)

    # Legenda precisa citar a LUI quando existe liberação de modelo
    if profile_value(profile, "exige_lui_na_legenda"):
        tem_liberacao = (fields.model_release or "").strip() not in (
            "", "Not Applicable", "None")
        if tem_liberacao and "lui:" not in caption.lower():
            issues.append(
                "Há liberação de modelo declarada, mas a legenda não cita a "
                "LUI. Acrescente \" - LUI: Nome\", com o mesmo nome do arquivo "
                "da licença.")

    if "digital_source" in required and not (fields.digital_source or "").strip():
        issues.append(
            "Origem digital não declarada. Agências recusam envio sem dizer se "
            "a imagem foi gerada ou alterada por IA.")
    if "object_name" in required and not (fields.object_name or "").strip():
        issues.append("Título de venda não preenchido.")
    if "model_release" in required and not (fields.model_release or "").strip():
        issues.append(
            "Liberação de modelo não declarada. Foto com pessoa reconhecível "
            "sem status é recusada.")
    if "alt_text" in required and not (fields.alt_text or "").strip():
        issues.append("Texto alternativo de acessibilidade não preenchido.")

    if "creator" in required and not (fields.creator or "").strip():
        issues.append("Criador (fotógrafo/autor) não preenchido.")

    if "city" in required and not (fields.city or "").strip():
        issues.append("Cidade não preenchida.")
    if "state" in required and not (fields.state or "").strip():
        issues.append("Estado/Província não preenchido.")
    if "country" in required and not (fields.country or "").strip():
        issues.append("País não preenchido.")

    if fields.date_created is None:
        issues.append(
            "Data de criação não encontrada no EXIF da câmera — confira se a câmera "
            "estava com data/hora configuradas corretamente."
        )

    if profile["min_edge"]:
        if shorter_edge is None:
            issues.append("Não foi possível determinar a resolução da imagem.")
        elif shorter_edge < profile["min_edge"]:
            issues.append(
                f"Menor borda da imagem é {shorter_edge}px "
                f"(mínimo exigido pelo perfil ativo: {profile['min_edge']}px)."
            )

    return issues


# ---------------------------------------------------------------- gravação

def _write_selected_fields(
    path: str,
    fields: PhotoFields,
    apply_fields: Set[str],
    keep_backup: bool,
    include_date: bool,
    custom_fields: Optional[Dict[str, str]] = None,
) -> None:
    charset_args = ["-charset", "iptc=UTF8", "-codedcharacterset=utf8", "-charset", "utf8"]

    step1 = list(charset_args)
    if not keep_backup:
        step1.append("-overwrite_original")

    wrote_something = False
    for key, tags in SCALAR_FIELD_TAGS.items():
        if key not in apply_fields:
            continue
        value = (getattr(fields, key) or "").strip()
        for tag in tags:
            step1.append(f"-{tag}={value}")
        wrote_something = True

    if "keywords" in apply_fields:
        for tag in KEYWORDS_TAGS:
            step1.append(f"-{tag}=")  # limpa a lista antes de reconstruir
        wrote_something = True

    for tag, value in (custom_fields or {}).items():
        if not is_valid_tag_name(tag):
            raise MetadataWriteError(f"Nome de tag inválido em campo personalizado: '{tag}'")
        step1.append(f"-{tag.strip()}={value}")
        wrote_something = True

    if include_date and fields.date_created:
        date_str = fields.date_created.strftime("%Y:%m:%d")
        time_str = fields.date_created.strftime("%H:%M:%S")
        step1 += [
            f"-IPTC:DateCreated={date_str}",
            f"-IPTC:TimeCreated={time_str}",
            f"-XMP-photoshop:DateCreated={fields.date_created.strftime('%Y:%m:%dT%H:%M:%S')}",
        ]
        wrote_something = True

    if wrote_something:
        step1.append(path)
        _run_exiftool(step1)

    # A limpeza de uma lista (-TAG=) e a adição de itens (-TAG+=) na MESMA
    # chamada do ExifTool não funcionam como se poderia esperar — testes
    # mostraram que, juntas no mesmo comando, o ExifTool ignora a limpeza e
    # só aplica a adição, resultando em palavras-chave acumuladas. Por isso
    # a adição das keywords é uma segunda chamada separada.
    if "keywords" in apply_fields:
        clean_keywords = [kw.strip() for kw in fields.keywords if kw.strip()]
        if clean_keywords:
            step2 = list(charset_args) + ["-overwrite_original"]
            for kw in clean_keywords:
                for tag in KEYWORDS_TAGS:
                    step2.append(f"-{tag}+={kw}")
            step2.append(path)
            _run_exiftool(step2)


def write_metadata(
    path: str,
    fields: PhotoFields,
    keep_backup: bool = True,
    custom_fields: Optional[Dict[str, str]] = None,
) -> None:
    """Grava TODOS os campos numa única foto (tela principal), mais
    quaisquer campos personalizados informados. Por padrão mantém uma
    cópia de segurança (<arquivo>_original) — comportamento nativo do
    ExifTool. A imagem em si nunca é reprocessada: apenas os blocos de
    metadado são reescritos."""
    _write_selected_fields(
        path, fields, apply_fields=set(ALL_FIELD_KEYS), keep_backup=keep_backup,
        include_date=True, custom_fields=custom_fields,
    )


@dataclass
class BatchItemResult:
    path: str
    ok: bool
    error: Optional[str] = None


def write_metadata_batch(
    paths: List[str],
    fields: PhotoFields,
    apply_fields: Set[str],
    keep_backup: bool = True,
    custom_fields: Optional[Dict[str, str]] = None,
) -> List[BatchItemResult]:
    """Grava só os campos marcados pelo usuário ('aplicar a todas'), mais
    quaisquer campos personalizados informados, em cada arquivo da lista.
    Campos não marcados não são tocados — o valor que já existia em cada
    foto (ex.: legenda individual) permanece intacto. A Data nunca é
    gravada em lote (é sempre por foto, lida da câmera). Um arquivo com
    erro não interrompe o processamento dos demais."""
    results = []
    for path in paths:
        try:
            _write_selected_fields(
                path, fields, apply_fields=apply_fields, keep_backup=keep_backup,
                include_date=False, custom_fields=custom_fields,
            )
            results.append(BatchItemResult(path=path, ok=True))
        except (ExifToolNotFound, MetadataWriteError) as e:
            results.append(BatchItemResult(path=path, ok=False, error=str(e)))
    return results


def write_batch_log_csv(csv_path: str, results: List[BatchItemResult], applied_fields: List[str]) -> None:
    applied_label = "; ".join(FIELD_LABELS.get(k, k) for k in applied_fields)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["arquivo", "status", "erro", "campos_aplicados_em_lote"])
        for r in results:
            writer.writerow([os.path.basename(r.path), "OK" if r.ok else "ERRO", r.error or "", applied_label])


# ------------------------------------------------------------- preferências

def _prefs_path() -> str:
    return os.path.join(platform_utils.get_app_dir(), "preferencias.json")


_PREFS_KEYS = ["creator", "creator_url", "city", "state", "country", "copyright", "credit", "source", "usage_terms", "profile"]


def load_prefs() -> dict:
    defaults = {k: "" for k in _PREFS_KEYS}
    defaults["profile"] = DEFAULT_PROFILE
    path = _prefs_path()
    if not os.path.isfile(path):
        return defaults
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update({k: v for k, v in data.items() if k in defaults})
    except (OSError, ValueError):
        pass
    return defaults


def save_prefs(prefs: dict) -> None:
    path = _prefs_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({k: prefs.get(k, "") for k in _PREFS_KEYS}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # preferências não são críticas — falha ao salvar não deve travar o app
