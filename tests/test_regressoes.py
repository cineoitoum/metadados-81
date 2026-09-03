"""Regressões: um caso por defeito já encontrado em produção.

Cada teste aqui existe porque a falha correspondente chegou a passar
despercebida. Nenhum deles é hipotético.
"""

import os
import subprocess
import tempfile
from unittest import mock

import pytest

from PIL import Image

import metadata_engine as me
import platform_utils
import resize_engine as rz


# ------------------------------------------------------------- utilidades

@pytest.fixture
def foto(tmp_path):
    def _cria(nome="foto.jpg", largura=6000, altura=4200):
        caminho = tmp_path / nome
        Image.new("RGB", (largura, altura), (60, 90, 98)).save(caminho, quality=95)
        return str(caminho)
    return _cria


def _exiftool(*args):
    binario = me._find_exiftool()
    if not binario:
        pytest.skip("ExifTool não encontrado neste ambiente")
    return subprocess.run(
        platform_utils.exiftool_command(binario) + list(args),
        capture_output=True, text=True,
    ).stdout.strip()


# --------------------------------------------------------------- motores

def test_redimensionar_preserva_orientacao(foto):
    """A cópia excluía a tag Orientation, e toda foto vertical saía deitada."""
    origem = foto("vertical.jpg")
    _exiftool("-Orientation#=6", "-overwrite_original", origem)

    destino = rz.resize(origem, largura=3000)["destino"]

    assert _exiftool("-s3", "-Orientation", destino) == "Rotate 90 CW"


def test_redimensionar_preserva_metadados_do_original(foto):
    """O Pillow descarta tudo ao salvar; a cópia tem que trazer de volta."""
    origem = foto("com_dados.jpg")
    _exiftool("-IPTC:By-line=Testador", "-overwrite_original", origem)

    destino = rz.resize(origem, largura=3000)["destino"]

    assert _exiftool("-s3", "-IPTC:By-line", destino) == "Testador"


@pytest.mark.parametrize("valor", [0, -1, -100])
def test_tamanho_nao_positivo_e_recusado(valor):
    """Antes, 0 virava no-op silencioso e negativo virava uma imagem 1x1."""
    with pytest.raises(rz.ResizeError):
        rz.fit_size(6000, 4000, valor, None, True)


def test_ampliar_avisa(foto):
    """Ampliar JPEG só inventa pixel — o app permite, mas precisa dizer."""
    resultado = rz.resize(foto("pequena.jpg", 1000, 800), largura=5000)

    assert "AMPLIADA" in resultado["aviso"]


def test_reduzir_nao_avisa_de_ampliacao(foto):
    resultado = rz.resize(foto("grande.jpg", 6000, 4000), largura=3000)

    assert "AMPLIADA" not in resultado["aviso"]


def test_exiftool_travado_vira_erro_legivel():
    """Sem timeout, um ExifTool travado congelava a janela para sempre."""
    assert me.EXIFTOOL_TIMEOUT > 0

    with mock.patch("metadata_engine.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("exiftool", 60)):
        with pytest.raises(me.MetadataWriteError) as erro:
            me._run_exiftool(["-ver"])

    assert "não respondeu" in str(erro.value)


# ------------------------------------------------------------- interface

@pytest.fixture
def aba():
    """Uma aba de metadados de verdade, com a área de transferência
    isolada em disco temporário para não tocar na do usuário."""
    tk = pytest.importorskip("tkinter")
    platform_utils.register_bundled_fonts()
    import app as app_mod
    import clipboard_engine as ce

    try:
        janela = app_mod.App()
    except tk.TclError:  # pragma: no cover - ambiente sem display
        pytest.skip("sem display para o Tk")

    janela.update_idletasks()
    aba = janela.metadata_tab
    aba.clipboard = ce.Clipboard(
        path=os.path.join(tempfile.mkdtemp(), "transferencia.json"))
    yield aba
    janela.destroy()


def test_janela_de_lote_abre(aba):
    """Ficou quebrada por um NameError: o bloco de banco de imagens tinha
    sido colado do formulário de foto única, que usa outro container."""
    import tab_metadata

    janela = tab_metadata.BatchWindow(aba)
    aba.update_idletasks()
    try:
        assert set(janela.value_widgets) == set(tab_metadata.BATCH_FIELD_ORDER)
        janela._build_batch_fields()  # não pode estourar KeyError
    finally:
        janela.destroy()


def test_lote_cobre_os_campos_marcados_por_padrao():
    """BATCH_DEFAULT_CHECKED marcava campos que a tela nem exibia."""
    import tab_metadata

    assert me.BATCH_DEFAULT_CHECKED <= set(tab_metadata.BATCH_FIELD_ORDER)


def test_colar_duas_vezes_nao_duplica_campos(aba, foto):
    aba._open_photo(foto("origem.jpg"))
    aba.update_idletasks()
    aba.custom_editor.add_row("XMP:Rating", "4")
    aba.on_copy_metadata()

    aba._open_photo(foto("destino.jpg"))
    aba.update_idletasks()
    aba.on_paste_metadata()
    aba.on_paste_metadata()

    assert len(aba.custom_editor.rows) == 1


def test_campo_preenchido_sozinho_nao_conta_como_edicao(aba, foto):
    """Os campos fixos (criador, cidade, copyright) vêm preenchidos das
    preferências e quase nunca estão na foto ainda. Contá-los como
    edição pendente fazia o aviso disparar em TODA foto, e o botão de
    redimensionar parecia quebrado: só abria um diálogo."""
    aba._open_photo(foto("recem_aberta.jpg"))
    aba.update_idletasks()

    assert aba._form_differs_from_file() is False


def test_texto_digitado_conta_como_edicao(aba, foto):
    aba._open_photo(foto("editada.jpg"))
    aba.update_idletasks()
    aba.caption_text.insert("1.0", "texto que não pode sumir")

    assert aba._form_differs_from_file() is True


def test_redimensionar_sem_edicao_nao_pergunta_nada(aba, foto, tmp_path):
    """O sintoma relatado: clicar em aplicar e não acontecer nada."""
    import tab_metadata

    caminho = foto("redim.jpg")
    aba._open_photo(caminho)
    aba.update_idletasks()
    aba.resize_w.delete(0, "end")
    aba.resize_w.insert(0, "3000")

    with mock.patch.object(aba, "_ask_metadata_choice") as pergunta, \
         mock.patch.object(tab_metadata.messagebox, "showinfo"), \
         mock.patch.object(tab_metadata.messagebox, "showerror"), \
         mock.patch.object(tab_metadata.messagebox, "askyesno", return_value=True):
        aba.on_resize()

    assert not pergunta.called, "não devia perguntar nada — nada foi digitado"
    assert os.path.exists(str(tmp_path / "redim_redim.jpg")), "a foto não foi gerada"


def test_campo_personalizado_ja_salvo_nao_conta_como_pendente(aba, foto):
    import tab_metadata

    caminho = foto("salva.jpg")
    aba._open_photo(caminho)
    aba.update_idletasks()
    aba.caption_text.insert("1.0", "legenda")
    aba.custom_editor.add_row("XMP:Rating", "4")

    with mock.patch.object(tab_metadata.messagebox, "showinfo"), \
         mock.patch.object(tab_metadata, "show_issues_dialog", return_value=True):
        aba.on_save()

    assert aba._form_differs_from_file() is False


def test_data_invalida_avisa_em_vez_de_sumir(aba, foto):
    import tab_metadata

    aba._open_photo(foto("data.jpg"))
    aba.update_idletasks()
    aba.date_entry.delete(0, "end")
    aba.date_entry.insert(0, "32/13/2026")

    with mock.patch.object(tab_metadata.messagebox, "showwarning") as aviso:
        assert aba._parse_date_entry() is None

    assert aviso.called
