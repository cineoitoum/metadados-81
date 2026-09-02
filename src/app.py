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
        ttk.Button(cabecalho, text="Sobre", style="ContainerGhost.TButton",
                   command=self._show_about).pack(side="right")

        self._build_menubar()

        self.metadata_tab = MetadataTab(self)
        self.metadata_tab.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menubar(self):
        """Monta a barra de menus do sistema.

        DUAS RAZÕES, e a primeira é um crash de verdade:

        1. No macOS, um app EMPACOTADO sem menu de aplicativo faz o Tk
           tentar montar um sozinho e abortar em
           NSMenuItem initWithTitle: com título nulo. Rodando do
           código-fonte não acontece — só dentro do .app, que é
           exatamente onde o usuário abre. O menu "apple" precisa existir,
           nem que seja vazio.

        2. Sem um menu Editar, ⌘X/⌘C/⌘V NÃO funcionam nos campos de texto
           do Tk no macOS. O Tk depende dos itens de menu para disparar os
           eventos virtuais de recortar, copiar e colar.
        """
        menubar = tk.Menu(self)

        if platform_utils.is_macos():
            # precisa chamar-se "apple" — é o nome que o Tk procura
            apple = tk.Menu(menubar, name="apple")
            menubar.add_cascade(menu=apple)
            apple.add_command(label="Sobre o %s" % theme.APP_NAME,
                              command=self._show_about)
            apple.add_separator()

        editar = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Editar", menu=editar)
        for rotulo, evento, atalho in (
            ("Recortar", "<<Cut>>", "Command-x"),
            ("Copiar", "<<Copy>>", "Command-c"),
            ("Colar", "<<Paste>>", "Command-v"),
        ):
            editar.add_command(
                label=rotulo,
                accelerator="⌘" + atalho[-1].upper() if platform_utils.is_macos()
                            else "Ctrl+" + atalho[-1].upper(),
                command=lambda e=evento: self._post_event(e))
        editar.add_separator()
        editar.add_command(label="Selecionar tudo",
                           command=lambda: self._post_event("<<SelectAll>>"))

        self.configure(menu=menubar)

    def _post_event(self, evento):
        """Dispara o evento virtual no widget que está com o foco."""
        alvo = self.focus_get()
        if alvo is not None:
            try:
                alvo.event_generate(evento)
            except tk.TclError:
                pass

    def _show_about(self):
        """Janela própria em vez de messagebox: o texto é longo demais
        para um alerta do sistema, e o endereço precisa ser clicável."""
        if getattr(self, "_about_window", None) is not None:
            try:
                if self._about_window.winfo_exists():
                    self._about_window.lift()
                    self._about_window.focus_force()
                    return
            except tk.TclError:
                pass

        janela = tk.Toplevel(self)
        self._about_window = janela
        janela.title("Sobre o %s" % theme.APP_NAME)
        janela.configure(bg=theme.BG_APP)
        janela.minsize(560, 520)
        janela.transient(self)

        rodape = ttk.Frame(janela, style="Container.TFrame", padding=(14, 10))
        rodape.pack(side="bottom", fill="x")
        ttk.Button(rodape, text="Fechar", style="Neon.TButton",
                   command=janela.destroy).pack(side="right")
        ttk.Label(rodape, text="Licença MIT",
                  style="ContainerDim.TLabel").pack(side="left")

        corpo = ttk.Frame(janela, padding=(18, 16))
        corpo.pack(fill="both", expand=True)

        faixa = theme.card(corpo, fill=theme.PEACH, padding=16)
        faixa.pack(fill="x")
        ttk.Label(faixa, text=theme.APP_NAME, style="PeachTitle.TLabel").pack(anchor="w")
        ttk.Label(faixa, text="Versão 1.0  ·  macOS e Windows",
                  style="Peach.TLabel").pack(anchor="w")

        def bloco(titulo, texto, primeiro=False):
            if titulo:
                ttk.Label(corpo, text=titulo, style="Section.TLabel").pack(
                    anchor="w", pady=(14 if not primeiro else 12, 3))
            ttk.Label(corpo, text=texto, wraplength=500, justify="left").pack(anchor="w")

        bloco("", "Editor de metadados IPTC e XMP para fotografia. Preenche os "
                  "campos que bancos de imagem, redações e arquivos exigem — e "
                  "copia esses dados de uma foto para a próxima.", primeiro=True)

        bloco("O que faz",
              "• Legenda, título, palavras-chave, autor, local, direitos, "
              "crédito e termos de uso, gravados em IPTC e XMP ao mesmo tempo.\n"
              "• Copiar e colar metadados entre fotos, com a área de "
              "transferência sobrevivendo ao fechar o programa.\n"
              "• Campos que as agências passaram a exigir: declaração de origem "
              "digital (IA), texto alternativo de acessibilidade e status de "
              "liberação de modelo e propriedade.\n"
              "• Perfis de validação por agência — Adobe Stock, Shutterstock e "
              "Getty — com os limites de cada uma.\n"
              "• Processamento em lote, escolhendo por campo o que se repete.\n"
              "• Ficha técnica completa do arquivo e redimensionamento com "
              "proporção travada.")

        bloco("Como trata suas fotos",
              "Os pixels não são recomprimidos. O ExifTool reescreve apenas os "
              "blocos de metadado, e a imagem permanece byte a byte idêntica. A "
              "única exceção é o redimensionamento, que por definição recodifica "
              "— e por isso grava uma cópia em vez de sobrescrever.\n\n"
              "Nada é enviado para a internet. Não há conta, telemetria nem "
              "sincronização: seus dados ficam apenas neste computador.")

        ttk.Separator(corpo).pack(fill="x", pady=(16, 0))

        bio = theme.card(corpo, padding=14)
        bio.pack(fill="x", pady=(14, 0))
        ttk.Label(bio, text="Sobre o autor", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            bio,
            text="Gustavo Serrate é cineasta e fotógrafo, fundador da CINE 81, "
                 "produtora audiovisual brasiliense atuando desde 2012 com "
                 "produção documental e trabalhos institucionais para "
                 "instituições governamentais, embaixadas, ONGs, organismos "
                 "internacionais e projetos culturais.",
            style="Card.TLabel", wraplength=470, justify="left",
        ).pack(anchor="w", pady=(6, 8))

        link = ttk.Label(bio, text="www.cineoitoum.org", style="CardAccent.TLabel",
                         cursor="pointinghand")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda _e: self._abrir_site("https://www.cineoitoum.org"))

    def _abrir_site(self, url):
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            pass

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
