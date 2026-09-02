"""
Área de transferência de metadados.

O gesto que este módulo existe para servir: você acabou de etiquetar uma
foto e a próxima é do mesmo trabalho — mesmo autor, mesma cidade, mesmos
direitos, quase a mesma legenda. Copiar e colar evita redigitar.

Guarda um PhotoFields inteiro mais os campos personalizados, e lembra de
qual arquivo veio. Persiste em disco de propósito: é comum copiar de uma
foto hoje e colar noutra amanhã, e uma área de transferência que se perde
ao fechar o app não serviria pra isso.

O que NÃO entra na cópia: a data de captura e o GPS. Esses vêm da câmera
e são de cada foto — copiá-los produziria metadado errado, que é pior que
metadado ausente.
"""

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import platform_utils
from metadata_engine import PhotoFields

FILENAME = "area_transferencia.json"

# campos que fazem sentido copiar entre fotos
COPYABLE_KEYS = [
    "caption", "headline", "instructions", "keywords",
    "creator", "creator_url", "city", "state", "country",
    "copyright", "credit", "source", "usage_terms",
]


class Clipboard:
    """Um slot só, como a área de transferência do sistema."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(platform_utils.get_app_dir(), FILENAME)
        self.fields: Optional[PhotoFields] = None
        self.custom: Dict[str, str] = {}
        self.source_name: str = ""
        self.copied_at: str = ""

    # ------------------------------------------------------------- estado

    def is_empty(self) -> bool:
        return self.fields is None

    def filled_keys(self) -> List[str]:
        """Quais campos têm conteúdo — o que a interface mostra como
        resumo do que está guardado."""
        if self.fields is None:
            return []
        cheios = []
        for chave in COPYABLE_KEYS:
            valor = getattr(self.fields, chave, None)
            if chave == "keywords":
                if valor:
                    cheios.append(chave)
            elif valor:
                cheios.append(chave)
        return cheios

    def summary(self) -> str:
        """Uma linha descrevendo o conteúdo, pra barra de status."""
        if self.is_empty():
            return "Área de transferência vazia."
        quantos = len(self.filled_keys()) + len(self.custom)
        origem = (' de "%s"' % self.source_name) if self.source_name else ""
        quando = (" · %s" % self.copied_at[:16]) if self.copied_at else ""
        return "%d campo(s)%s%s" % (quantos, origem, quando)

    # -------------------------------------------------------------- copiar

    def copy_from(self, fields: PhotoFields, custom: Optional[dict] = None,
                  source_name: str = "") -> None:
        """Guarda uma cópia. Data e GPS ficam de fora — ver o cabeçalho."""
        copia = PhotoFields()
        for chave in COPYABLE_KEYS:
            valor = getattr(fields, chave, None)
            if chave == "keywords":
                setattr(copia, chave, list(valor or []))
            else:
                setattr(copia, chave, valor or "")
        self.fields = copia
        self.custom = dict(custom or {})
        self.source_name = source_name
        self.copied_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save()

    def clear(self) -> None:
        self.fields = None
        self.custom = {}
        self.source_name = ""
        self.copied_at = ""
        self.save()

    # --------------------------------------------------------------- colar

    def paste_onto(self, alvo: PhotoFields, apenas: Optional[List[str]] = None) -> PhotoFields:
        """Aplica o que está guardado sobre um PhotoFields.

        Campo vazio na área de transferência NÃO apaga o que está no
        destino: colar deve acrescentar o que se copiou, não zerar o que
        já havia. Pra limpar um campo, o usuário apaga na tela.
        """
        if self.fields is None:
            return alvo
        chaves = apenas if apenas is not None else COPYABLE_KEYS
        for chave in chaves:
            valor = getattr(self.fields, chave, None)
            if chave == "keywords":
                if valor:
                    alvo.keywords = list(valor)
            elif valor:
                setattr(alvo, chave, valor)
        return alvo

    # ----------------------------------------------------------- persistência

    def save(self) -> None:
        """Falha em silêncio: perder a área de transferência é um
        inconveniente, não um erro que valha interromper o trabalho."""
        try:
            if self.fields is None:
                if os.path.isfile(self.path):
                    os.remove(self.path)
                return
            dados = asdict(self.fields)
            dados.pop("date_created", None)   # não se copia data de captura
            payload = {
                "versao": 1,
                "campos": dados,
                "personalizados": self.custom,
                "origem": self.source_name,
                "copiado_em": self.copied_at,
            }
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            temporario = self.path + ".tmp"
            with open(temporario, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(temporario, self.path)
        except OSError:
            pass

    def load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(dados, dict):
            return
        campos = dados.get("campos") or {}
        if not isinstance(campos, dict):
            return
        limpos = {k: v for k, v in campos.items()
                  if k in PhotoFields.__dataclass_fields__ and k != "date_created"}
        try:
            self.fields = PhotoFields(**limpos)
        except TypeError:
            return
        personalizados = dados.get("personalizados") or {}
        self.custom = {str(k): str(v) for k, v in personalizados.items()} \
            if isinstance(personalizados, dict) else {}
        self.source_name = dados.get("origem", "") or ""
        self.copied_at = dados.get("copiado_em", "") or ""
