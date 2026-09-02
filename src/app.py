"""
Metadados 81 — edição de metadados IPTC/XMP de fotos.

Um programa só, uma janela só. É a aba de Metadados do Metadata Foto 81
(hoje CineBrain OS) recortada em produto próprio, mais a área de
transferência: copiar os metadados de uma foto e colar na próxima.

Escreve apenas os blocos de metadado (APP1/IPTC/XMP) via ExifTool. A
imagem em si não é recomprimida — permanece byte a byte idêntica.

Dependências: Python 3.9+ com Tcl/Tk 8.6+, Pillow, ExifTool (embutido no
app empacotado).
"""

import sys
import tkinter as tk
from tkinter import messagebox, ttk

import platform_utils
import theme
from tab_metadata import MetadataTab
from ui_common import DND_AVAILABLE, TkinterDnD

_BaseTk = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk

MIN_TK_VERSION = (8, 6)


class App(_BaseTk):
    def __init__(self):
        super().__init__()
        self.title(theme.APP_NAME)
        self.geometry("1120x880")
        self.minsize(900, 640)
        theme.apply(self)

        cabecalho = ttk.Frame(self, style="Container.TFrame", padding=(14, 8))
        cabecalho.pack(fill="x")
        ttk.Label(cabecalho, text=theme.APP_NAME, style="Container.TLabel",
                  font=theme.FONT_SECTION).pack(side="left")
        ttk.Label(cabecalho, text="  metadados IPTC/XMP",
                  style="ContainerDim.TLabel").pack(side="left")

        self.metadata_tab = MetadataTab(self)
        self.metadata_tab.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        # grava as preferências de campos "de casa" antes de sair
        self.metadata_tab.on_app_close()
        self.destroy()


def _check_tk_version():
    """O Tcl/Tk 8.5 de sistema do macOS (congelado na 8.5.9 em 2010) não
    desenha o conteúdo das janelas: o app abre inteiramente em branco, sem
    erro nenhum. Como o sintoma não sugere a causa, vale detectar."""
    probe = tk.Tk()
    try:
        patchlevel = probe.tk.call("info", "patchlevel")
    except tk.TclError:
        patchlevel = "desconhecida"
    try:
        partes = tuple(int(p) for p in str(patchlevel).split(".")[:2])
    except ValueError:
        partes = (0, 0)

    if partes >= MIN_TK_VERSION:
        probe.destroy()
        return True

    probe.withdraw()
    messagebox.showerror(
        "Tcl/Tk desatualizado",
        "Este Python está usando Tcl/Tk %s, e o %s precisa da 8.6 ou "
        "superior.\n\nNa 8.5 as janelas abrem completamente em branco — é "
        "uma limitação conhecida do Tk antigo que a Apple mantém no "
        "sistema, não um defeito do app.\n\nComo resolver no macOS:\n"
        "    brew install python-tk\n"
        "e rode com o Python do Homebrew, não com o /usr/bin/python3."
        % (patchlevel, theme.APP_NAME),
    )
    probe.destroy()
    return False


def _smoke_test():
    """Prova que o app EMPACOTADO funciona. Roda no fim do build."""
    falhas = []

    fontes = platform_utils.register_bundled_fonts()
    if fontes:
        print("  fontes embutidas  : %s" % ", ".join(fontes))
    elif getattr(sys, "frozen", False):
        falhas.append("nenhuma fonte embutida foi registrada")
    else:
        print("  fontes embutidas  : nenhuma (rodando do código-fonte)")

    try:
        import metadata_engine
        binario = metadata_engine._find_exiftool()
        if not binario:
            falhas.append("ExifTool não encontrado")
        else:
            versao = metadata_engine._run_exiftool(["-ver"]).strip()
            embutido = "_MEI" in binario or "exiftool_bundle" in binario
            print("  ExifTool          : %s (%s)"
                  % (versao, "embutido" if embutido else "do sistema"))
            if getattr(sys, "frozen", False) and not embutido:
                falhas.append("o ExifTool embutido não foi usado")
    except Exception as e:
        falhas.append("ExifTool não respondeu: %s" % e)

    if not _check_tk_version():
        return 1

    try:
        app = App()
        app.update_idletasks()
        print("  janela            : montou")
        print("  área de transf.   : %s" % app.metadata_tab.clipboard.summary())
        app.destroy()
    except Exception:
        import traceback
        traceback.print_exc()
        falhas.append("a janela não montou")

    if falhas:
        print("smoke-test FALHOU:")
        for f in falhas:
            print("  - %s" % f)
        return 1
    print("smoke-test OK")
    return 0


def main():
    # ORDEM CRÍTICA: as fontes precisam ser registradas ANTES de qualquer
    # Tk existir. O Tk monta a lista de famílias na criação do
    # interpretador; registrar depois retorna sucesso e a fonte não
    # aparece.
    platform_utils.register_bundled_fonts()

    if "--smoke-test" in sys.argv:
        sys.exit(_smoke_test())

    if not _check_tk_version():
        return
    App().mainloop()


if __name__ == "__main__":
    main()
