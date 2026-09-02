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
}

# Campos que fazem sentido repetir automaticamente entre fotos de um mesmo
# lote (mesmo local/autor/condições) — os demais (texto único por foto)
# começam desmarcados por padrão na tela de lote.
BATCH_DEFAULT_CHECKED = {
    "keywords", "creator", "creator_url", "sublocation", "city", "state",
    "country", "country_code",
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
}
DEFAULT_PROFILE = "padrao"


def list_profiles() -> List[tuple]:
    return [(key, cfg["label"]) for key, cfg in VALIDATION_PROFILES.items()]


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

def validate(fields: PhotoFields, shorter_edge: Optional[int], profile_key: str = DEFAULT_PROFILE) -> List[str]:
    """Retorna lista de problemas encontrados, de acordo com o perfil de
    validação ativo. Lista vazia = tudo certo."""
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
