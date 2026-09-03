"""
Utilidades de interface compartilhadas entre as abas do app (arrastar-e-
soltar, editor de campos personalizados, diálogo de itens pendentes).
"""

import tkinter as tk
from tkinter import ttk

import theme

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    DND_FILES = None
    TkinterDnD = None


def tab_toolbar(parent, title, subtitle=""):
    """A faixa steel do topo de cada aba.

    Existe para dar às abas herdadas o mesmo ritmo das novas sem
    reescrevê-las: um bloco steel identifica onde você está, e o resto da
    aba continua como estava. Devolve a faixa, para quem quiser pendurar
    botões nela pela direita."""
    barra = ttk.Frame(parent, style="Container.TFrame", padding=(14, 10))
    barra.pack(fill="x")
    texto = ttk.Frame(barra, style="Container.TFrame")
    texto.pack(side="left")
    ttk.Label(texto, text=title, style="Container.TLabel",
              font=theme.FONT_SECTION).pack(anchor="w")
    if subtitle:
        ttk.Label(texto, text=subtitle, style="ContainerDim.TLabel",
                  wraplength=820, justify="left").pack(anchor="w", pady=(2, 0))
    return barra


def bind_mousewheel(canvas, content_widget=None, responsivo=True):
    """Rolagem pela roda/trackpad num Canvas rolável, e opcionalmente faz
    o conteúdo acompanhar a largura da janela.

    A ROLAGEM É POR PLATAFORMA, e isso importa: o valor de `event.delta`
    não significa a mesma coisa em cada sistema.

        macOS    incrementos pequenos, já na escala de "linhas"
        Windows  múltiplos de 120 por entalhe da roda
        Linux    não usa delta — manda Button-4 (cima) e Button-5 (baixo)

    O código anterior fazia `yview_scroll(-event.delta)` cru. No macOS
    ficava aceitável mas irregular; no Windows dispararia 120 linhas por
    entalhe. Agora cada sistema usa a sua convenção, que é o que o
    usuário já espera de qualquer outro programa da máquina.
    """

    def _passos(event):
        if getattr(event, "num", None) == 4:
            return -1
        if getattr(event, "num", None) == 5:
            return 1
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return 0
        if abs(delta) >= 120:          # Windows
            return -int(delta / 120)
        return -int(delta)             # macOS

    def _on_wheel(event):
        passos = _passos(event)
        if passos:
            canvas.yview_scroll(passos, "units")
        return "break"

    def _bind_recursive(widget):
        widget.bind("<MouseWheel>", _on_wheel, add="+")
        widget.bind("<Button-4>", _on_wheel, add="+")
        widget.bind("<Button-5>", _on_wheel, add="+")
        for child in widget.winfo_children():
            _bind_recursive(child)

    canvas.bind("<MouseWheel>", _on_wheel, add="+")
    canvas.bind("<Button-4>", _on_wheel, add="+")
    canvas.bind("<Button-5>", _on_wheel, add="+")
    if content_widget is not None:
        _bind_recursive(content_widget)

    if responsivo:
        make_responsive(canvas)


def make_responsive(canvas):
    """Faz o conteúdo de um Canvas rolável acompanhar a largura dele.

    Quase toda aba monta o conteúdo com
    `canvas.create_window(..., width=900)` — largura fixa. Ao alargar a
    janela sobra fundo vazio à direita; ao estreitar, o conteúdo é
    cortado em vez de se reajustar.

    Em vez de editar cada aba, isto descobre os itens de janela do canvas
    e reamarra a largura deles. Como toda aba já chama bind_mousewheel,
    a correção alcança todas de uma vez.
    """
    try:
        janelas = [i for i in canvas.find_all() if canvas.type(i) == "window"]
    except tk.TclError:
        return
    if not janelas:
        return

    def _ajustar(event):
        for item in janelas:
            try:
                canvas.itemconfigure(item, width=event.width)
            except tk.TclError:
                pass

    canvas.bind("<Configure>", _ajustar, add="+")


def extract_dropped_paths(event) -> list:
    """Converte o event.data de um <<Drop>> do tkinterdnd2 (formato Tcl,
    com chaves em volta de caminhos com espaço) numa lista de strings."""
    widget = event.widget
    try:
        return list(widget.tk.splitlist(event.data))
    except Exception:
        return [event.data]


class CustomFieldsEditor:
    """Painel reutilizável de 'campos avançados': o padrãozinho fixo do
    app cobre o básico, mas o usuário pode gravar QUALQUER tag do ExifTool
    (nome + valor), quantas quiser. Usado na aba de Metadados (single e
    lote)."""

    def __init__(self, parent, hint_text, titulo="Campos avançados (personalizados) — opcional:"):
        self.container = ttk.Frame(parent)
        self.rows = []  # (row_frame, tag_entry, value_entry)

        header = ttk.Frame(self.container)
        header.pack(fill="x")
        if titulo:
            ttk.Label(header, text=titulo).pack(side="left")
        ttk.Button(header, text="+ Adicionar campo", command=self.add_row).pack(side="right")

        ttk.Label(self.container, text=hint_text, foreground=theme.FG_DIM, wraplength=650, justify="left").pack(anchor="w")

        self.rows_frame = ttk.Frame(self.container)
        self.rows_frame.pack(fill="x", pady=(4, 0))

    def pack(self, **kwargs):
        self.container.pack(**kwargs)

    def add_row(self, tag="", value=""):
        row = ttk.Frame(self.rows_frame)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Tag ExifTool:").pack(side="left")
        tag_entry = ttk.Entry(row, width=26)
        tag_entry.pack(side="left", padx=(4, 10))
        tag_entry.insert(0, tag)
        ttk.Label(row, text="Valor:").pack(side="left")
        value_entry = ttk.Entry(row)
        value_entry.pack(side="left", fill="x", expand=True, padx=(4, 10))
        value_entry.insert(0, value)

        entry = (row, tag_entry, value_entry)

        def remove():
            row.destroy()
            self.rows.remove(entry)

        ttk.Button(row, text="remover", width=8, command=remove).pack(side="left")
        self.rows.append(entry)

    def clear(self):
        for row, _tag, _val in self.rows:
            row.destroy()
        self.rows = []

    def collect(self) -> dict:
        result = {}
        for _row, tag_entry, value_entry in self.rows:
            tag = tag_entry.get().strip()
            if tag:
                result[tag] = value_entry.get().strip()
        return result


def _resolver(opcoes):
    """Aceita lista pronta ou função que devolve a lista."""
    try:
        valores = opcoes() if callable(opcoes) else opcoes
        return [str(v) for v in (valores or [])]
    except Exception:
        return []


class DynamicRows(ttk.Frame):
    """Tabela onde o usuário acrescenta e remove linhas à vontade.

    Usada pelas entregas, orçamento e equipe do Funil, e pelas tabelas de
    equipe e shotlist da Ordem do Dia — sempre que o número de linhas
    depende do trabalho e não dá pra fixar no código.

    colunas: [(chave, título, largura), ...] ou
             [(chave, título, largura, opcoes), ...] para lista suspensa,
             onde `opcoes` é uma função sem argumentos que devolve a lista
             — função, e não lista fixa, porque as opções podem mudar
             enquanto a janela está aberta (as locações da Ordem do Dia
             são digitadas na mesma tela que a shotlist).
    com_checkbox: (chave, título) pra uma caixa no começo da linha
    ao_mudar: chamado a cada digitação, pra recalcular totais ao vivo
    conversor: aplicado às chaves listadas em `numericos` no collect()
    """

    def __init__(self, parent, colunas, com_checkbox=None, ao_mudar=None,
                 conversor=float, estilo_card=True):
        estilo = "Card.TFrame" if estilo_card else "TFrame"
        super().__init__(parent, style=estilo)
        self.colunas = colunas
        self.com_checkbox = com_checkbox
        self.ao_mudar = ao_mudar
        self.conversor = conversor
        self._estilo = estilo
        self._estilo_label = "CardDim.TLabel" if estilo_card else "Dim.TLabel"
        self._estilo_entry = "Card.TEntry" if estilo_card else "TEntry"
        self._estilo_check = "Card.TCheckbutton" if estilo_card else "TCheckbutton"
        self._estilo_botao = "CardGhost.TButton" if estilo_card else "Ghost.TButton"
        self.linhas = []

        self._estilo_combo = "Card.TCombobox" if estilo_card else "TCombobox"

        cabecalho = ttk.Frame(self, style=estilo)
        cabecalho.pack(fill="x")
        if com_checkbox:
            ttk.Label(cabecalho, text=com_checkbox[1], style=self._estilo_label,
                      width=6).pack(side="left")
        for coluna in colunas:
            titulo, largura = coluna[1], coluna[2]
            ttk.Label(cabecalho, text=titulo, style=self._estilo_label,
                      width=largura).pack(side="left", padx=2)

        self.corpo = ttk.Frame(self, style=estilo)
        self.corpo.pack(fill="x")

        ttk.Button(self, text="+ linha", style=self._estilo_botao,
                   command=self.add_row).pack(anchor="w", pady=(4, 0))

    def add_row(self, dados=None):
        linha = ttk.Frame(self.corpo, style=self._estilo)
        linha.pack(fill="x", pady=1)
        campos = {}

        check_var = None
        if self.com_checkbox:
            chave = self.com_checkbox[0]
            inicial = bool(getattr(dados, chave, False)) if dados is not None else False
            check_var = tk.BooleanVar(value=inicial)
            ttk.Checkbutton(linha, variable=check_var, style=self._estilo_check,
                            width=4).pack(side="left")

        for coluna in self.colunas:
            chave, largura = coluna[0], coluna[2]
            opcoes = coluna[3] if len(coluna) > 3 else None

            var = tk.StringVar()
            if dados is not None:
                valor = getattr(dados, chave, "")
                if isinstance(valor, float):
                    valor = ("%.2f" % valor) if valor else ""
                var.set("" if valor is None else str(valor))

            if opcoes is not None:
                combo = ttk.Combobox(linha, textvariable=var, width=largura - 2,
                                     style=self._estilo_combo)
                # a lista é resolvida na hora de abrir: as opções podem ter
                # mudado depois que esta linha foi criada
                combo.bind("<Button-1>",
                           lambda _e, c=combo, f=opcoes: c.configure(values=_resolver(f)))
                combo.configure(values=_resolver(opcoes))
                combo.pack(side="left", padx=2)
            else:
                ttk.Entry(linha, textvariable=var, style=self._estilo_entry,
                          width=largura).pack(side="left", padx=2)

            if self.ao_mudar:
                var.trace_add("write", lambda *_a: self.ao_mudar())
            campos[chave] = var

        registro = {"frame": linha, "campos": campos, "check": check_var}

        def remover():
            linha.destroy()
            if registro in self.linhas:
                self.linhas.remove(registro)
            if self.ao_mudar:
                self.ao_mudar()

        ttk.Button(linha, text="×", style="Danger.TButton", width=2,
                   command=remover).pack(side="left", padx=(4, 0))
        self.linhas.append(registro)
        return registro

    def load(self, itens):
        for registro in list(self.linhas):
            registro["frame"].destroy()
        self.linhas = []
        for item in itens or []:
            self.add_row(item)

    def collect(self, cls, numericos=()):
        """Monta os registros. Linha inteiramente em branco é descartada —
        senão sobrariam entradas vazias toda vez que alguém adiciona uma
        linha e desiste."""
        saida = []
        for registro in self.linhas:
            kwargs = {}
            vazio = True
            for chave, var in registro["campos"].items():
                valor = var.get().strip()
                if valor:
                    vazio = False
                if chave in numericos:
                    try:
                        kwargs[chave] = self.conversor(valor)
                    except (TypeError, ValueError):
                        kwargs[chave] = 0.0
                else:
                    kwargs[chave] = valor
            if vazio:
                continue
            if self.com_checkbox and registro["check"] is not None:
                kwargs[self.com_checkbox[0]] = bool(registro["check"].get())
            try:
                saida.append(cls(**kwargs))
            except TypeError:
                pass
        return saida


def show_issues_dialog(parent, title, issues) -> bool:
    """Mostra os problemas encontrados. Retorna True se o usuário quiser
    prosseguir mesmo assim, False se preferir voltar e corrigir."""
    dialog = tk.Toplevel(parent)
    dialog.configure(bg=theme.BG)
    dialog.title(title)
    dialog.minsize(520, 300)
    dialog.transient(parent)
    dialog.grab_set()

    result = {"proceed": False}

    def voltar():
        result["proceed"] = False
        dialog.destroy()

    def continuar():
        result["proceed"] = True
        dialog.destroy()

    # botões primeiro (side="bottom"), ANTES da área expansível — senão a
    # área expansível toma todo o espaço e os botões ficam espremidos.
    btns = ttk.Frame(dialog)
    btns.pack(side="bottom", fill="x", padx=15, pady=15)
    ttk.Button(btns, text="Voltar e corrigir", command=voltar).pack(side="left")
    ttk.Button(btns, text="Continuar mesmo assim", command=continuar).pack(side="right")

    ttk.Label(
        dialog,
        text="Encontrei os seguintes itens que não batem com o perfil de validação ativo:",
        wraplength=490,
        justify="left",
    ).pack(padx=15, pady=(15, 10), anchor="w")

    list_frame = ttk.Frame(dialog)
    list_frame.pack(fill="both", expand=True, padx=15)
    canvas = tk.Canvas(list_frame, highlightthickness=0)
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    for issue in issues:
        ttk.Label(inner, text="• " + issue, wraplength=460, justify="left").pack(anchor="w", pady=2)
    bind_mousewheel(canvas, inner)

    dialog.protocol("WM_DELETE_WINDOW", voltar)
    parent.wait_window(dialog)
    return result["proceed"]


def show_results_dialog(parent, title, message):
    """Diálogo simples de resumo, com texto rolável (útil pra listas
    grandes de resultado de lote/ingest/duplicatas/checklist)."""
    dialog = tk.Toplevel(parent)
    dialog.configure(bg=theme.BG)
    dialog.title(title)
    dialog.geometry("600x420")
    dialog.transient(parent)
    dialog.grab_set()

    # o botão precisa ser empacotado ANTES do texto expansível — senão o
    # texto toma todo o espaço da janela e o botão fica espremido a
    # quase-zero de altura (continua clicável, mas ilegível).
    ttk.Button(dialog, text="Fechar", command=dialog.destroy).pack(side="bottom", pady=15)

    text_frame = ttk.Frame(dialog)
    text_frame.pack(fill="both", expand=True, padx=15, pady=(15, 0))
    scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
    text = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
    scrollbar.configure(command=text.yview)
    text.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    text.insert("1.0", message)
    text.configure(state="disabled")

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
