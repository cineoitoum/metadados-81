"""
Tema visual do Metadados 81 — a mesma linguagem do CineBrain OS.

Derivado do pôster de referência: BURNT PEACH (#FE8254) sobre DEEP STEEL
BLUE (#3F5A62), os dois flutuando num chão creme.

O modelo é o inverso de um app escuro comum. Aqui o CHÃO é claro e calmo,
e a cor vem em BLOCOS que pousam nele:

  - creme (GROUND/SURFACE): o chão e as ilhas onde se lê e se preenche
  - steel: blocos de estrutura — barras, cabeçalhos, tabelas
  - peach: A AÇÃO. Uma por tela, para que "o que fazer agora" nunca fique
    ambíguo. Peach espalhado por toda parte perde exatamente essa função.

Três superfícies, três prefixos de estilo:

    ttk.Frame(parent)                           -> chão creme
    ttk.Frame(parent, style="Card.TFrame")      -> ilha creme clara
    ttk.Frame(parent, style="Container.TFrame") -> bloco steel

CONCESSÕES AO TKINTER, declaradas de propósito: ttk não tem canto
arredondado, nem recorte entrecruzado, nem sombra. O arredondado do
pôster é entregue por widgets.RoundedCard, que desenha no Canvas. Os
recortes entrecruzados foram descartados — em Canvas ficariam frágeis a
cada redimensionamento e pagariam pouco pelo custo.

Widgets tk "clássicos" (Text, Listbox, Canvas) não têm estilo nomeado —
para esses use style_text_card() / style_text_field().
"""

import tkinter as tk
from tkinter import ttk

import platform_utils

APP_NAME = platform_utils.APP_NAME

# --------------------------------------------------------------- paleta
# Retro-Modern Bento: burnt peach sobre deep steel blue, num chão creme.
#
# O modelo é o oposto do habitual em app escuro: o CHÃO é claro e calmo,
# e as cores fortes vêm em BLOCOS que flutuam nele. Steel carrega
# estrutura e leitura; peach carrega a ação da tela — uma por tela, para
# que "o que fazer agora" nunca fique ambíguo.

GROUND = "#E4DCC9"        # creme do fundo da janela (o chão)
SURFACE = "#EFE8D8"       # creme claro das ilhas/cards
FIELD = "#FBF7EE"         # quase branco — onde se digita
STEEL = "#3F5A62"         # deep steel blue: estrutura, blocos de leitura
PEACH = "#FE8254"         # burnt peach: a ação

# derivados — não são da marca, cobrem estados que os cinco acima não dão
STEEL_SOFT = "#5A757D"    # steel clareado: texto secundário sobre creme
STEEL_LINE = "#C9CFC9"    # borda fina sobre creme
STEEL_DEEP = "#2C4149"    # pressionado / texto muito forte
PEACH_SOFT = "#FFA079"    # peach clareado: hover
PEACH_DEEP = "#E8663A"    # peach escurecido: pressionado
ON_STEEL = "#FBF7EE"      # texto sobre blocos steel
ON_PEACH = "#3F5A62"      # texto sobre blocos peach (steel, como no pôster)
SUCCESS_C = "#4F7A5B"
WARNING_C = "#B8722A"
ERROR_C = "#C1462F"

RADIUS = 12               # raio dos cards (o pôster usa 16; 12 economiza
                          # borda sem perder o gesto arredondado)
RADIUS_PILL = 999         # pílulas e botões

# --- compatibilidade com o tema anterior -------------------------------
# As abas herdadas referenciam theme.BG/.FG/.FG_DIM diretamente. Apontam
# agora para os papéis equivalentes no chão claro, para que continuem
# legíveis até serem repaginadas uma a uma.
BG_APP = GROUND
BG_CONTAINER = STEEL
BG_CARD_LIGHT = SURFACE
TEXT_DARK = STEEL
TEXT_DARK_STRONG = STEEL_DEEP
TEXT_DARK_DIM = STEEL_SOFT
ACCENT_PRIMARY = PEACH
ACCENT_NEON = PEACH
FIELD_CARD = FIELD
BORDER_DARK = STEEL_LINE
BORDER_CARD = STEEL_LINE
SELECT_BG = PEACH
SELECT_BG_CARD = "#FFD9C8"
FG_ON_DARK = STEEL         # "sobre o chão" agora é escuro sobre claro
FG_DIM_ON_DARK = STEEL_SOFT
SUCCESS = SUCCESS_C
WARNING = WARNING_C
ERROR = ERROR_C

BG = GROUND
BG_PANEL = SURFACE
BG_HEADER = PEACH
FG = STEEL
FG_DIM = STEEL_SOFT
FG_ON_HEADER = ON_PEACH
BORDER = STEEL_LINE

# ---------------------------------------------------------------- fontes
# A interface usa a sans nativa de cada sistema (legível em formulário
# denso); a monoespaçada fica reservada pra dado técnico — caminho de
# arquivo, tag ExifTool, checksum.
#
# As famílias NÃO podem ser constantes fixas: "Helvetica Neue" e "Monaco"
# não existem no Windows, "Segoe UI" não existe no macOS. Os valores
# abaixo são só um ponto de partida por plataforma; apply() confere quais
# estão de fato instaladas (via tkinter.font.families(), que precisa de um
# root do Tk vivo) e reescreve estes globais antes de montar os estilos.
FONT_SIZE = 11
FONT_FAMILY_UI = platform_utils.ui_font_candidates()[0]
FONT_FAMILY_MONO = platform_utils.mono_font_candidates()[0]


def _rebuild_font_constants() -> None:
    """Recalcula as tuplas de fonte a partir das famílias resolvidas."""
    global FONT, FONT_BOLD, FONT_SMALL, FONT_TITLE, FONT_SECTION
    global FONT_MONO, FONT_FAMILY
    FONT = (FONT_FAMILY_UI, FONT_SIZE)
    FONT_BOLD = (FONT_FAMILY_UI, FONT_SIZE, "bold")
    FONT_SMALL = (FONT_FAMILY_UI, FONT_SIZE - 2)
    FONT_TITLE = (FONT_FAMILY_UI, FONT_SIZE + 4, "bold")
    FONT_SECTION = (FONT_FAMILY_UI, FONT_SIZE + 1, "bold")
    FONT_MONO = (FONT_FAMILY_MONO, FONT_SIZE - 1)
    # alias de compatibilidade: as abas herdadas montam fontes de título
    # com theme.FONT_FAMILY. Aponta pra família da interface, não a mono.
    FONT_FAMILY = FONT_FAMILY_UI


_rebuild_font_constants()


def _resolve_fonts(root: tk.Misc) -> None:
    """Escolhe a primeira família de cada lista que exista neste sistema.
    Se nenhuma existir, mantém o palpite — o Tk faz sua própria
    substituição e o app continua utilizável, só menos bonito."""
    global FONT_FAMILY_UI, FONT_FAMILY_MONO
    try:
        from tkinter import font as tkfont
        available = {name.lower() for name in tkfont.families(root)}
    except Exception:
        return

    for family in platform_utils.ui_font_candidates():
        if family.lower() in available:
            FONT_FAMILY_UI = family
            break
    for family in platform_utils.mono_font_candidates():
        if family.lower() in available:
            FONT_FAMILY_MONO = family
            break

    _rebuild_font_constants()

PAD = 8           # respiro padrão entre blocos
CARD_PAD = 9      # respiro interno dos cards


def apply(root: tk.Misc) -> ttk.Style:
    """Aplica o tema na janela raiz. Toplevels abertos depois herdam
    automaticamente (mesma base de opções do Tcl/Tk)."""
    root.configure(bg=BG_APP)

    # precisa vir antes de tudo: os estilos abaixo capturam as tuplas de
    # fonte por valor, então resolver depois não teria efeito
    _resolve_fonts(root)

    _apply_classic_widget_defaults(root)

    style = ttk.Style(root)
    # 'clam' é o único tema ttk que aceita reestilização de cores no
    # macOS — o tema nativo 'aqua' ignora a maioria das configurações.
    style.theme_use("clam")

    _apply_dark_surface(style)
    _apply_card_surface(style)
    _apply_buttons(style)
    _apply_notebook(style)
    _apply_treeview(style)

    return style


# --------------------------------------------- widgets tk "clássicos"

def _apply_classic_widget_defaults(root: tk.Misc) -> None:
    """Text, Listbox, Canvas e Menu só respondem ao banco de opções do
    Tcl. O padrão é a superfície onde se DIGITA (creme quase branco), que
    é o caso mais comum; para um bloco steel, chame style_text_steel()."""
    root.option_add("*Text.Background", FIELD)
    root.option_add("*Text.Foreground", STEEL)
    root.option_add("*Text.insertBackground", PEACH)
    root.option_add("*Text.selectBackground", SELECT_BG_CARD)
    root.option_add("*Text.selectForeground", STEEL_DEEP)
    root.option_add("*Text.Font", FONT)
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.borderWidth", 0)
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", STEEL_LINE)
    root.option_add("*Text.highlightColor", PEACH)

    root.option_add("*Listbox.Background", FIELD)
    root.option_add("*Listbox.Foreground", STEEL)
    root.option_add("*Listbox.selectBackground", PEACH)
    root.option_add("*Listbox.selectForeground", ON_PEACH)
    root.option_add("*Listbox.Font", FONT)
    root.option_add("*Listbox.relief", "flat")
    root.option_add("*Listbox.borderWidth", 0)
    root.option_add("*Listbox.highlightThickness", 1)
    root.option_add("*Listbox.highlightBackground", STEEL_LINE)

    root.option_add("*Canvas.Background", GROUND)
    root.option_add("*Canvas.highlightThickness", 0)

    root.option_add("*Menu.Background", SURFACE)
    root.option_add("*Menu.Foreground", STEEL)
    root.option_add("*Menu.Font", FONT)

    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", STEEL)
    root.option_add("*TCombobox*Listbox.selectBackground", PEACH)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_PEACH)
    root.option_add("*TCombobox*Listbox.font", FONT)


def style_text_card(widget) -> None:
    """Coloca um tk.Text/tk.Listbox numa ilha creme."""
    widget.configure(
        bg=FIELD, fg=STEEL, font=FONT,
        highlightthickness=1, highlightbackground=STEEL_LINE,
        highlightcolor=PEACH, relief="flat", borderwidth=0,
        selectbackground=SELECT_BG_CARD, selectforeground=STEEL_DEEP,
    )
    try:
        widget.configure(insertbackground=STEEL)
    except tk.TclError:
        pass


def style_text_steel(widget) -> None:
    """Coloca um tk.Text/tk.Listbox dentro de um bloco steel."""
    widget.configure(
        bg=STEEL_DEEP, fg=ON_STEEL, font=FONT,
        highlightthickness=0, relief="flat", borderwidth=0,
        selectbackground=PEACH, selectforeground=ON_PEACH,
    )
    try:
        widget.configure(insertbackground=PEACH)
    except tk.TclError:
        pass


# nome antigo, mantido pra não quebrar as abas ainda não repaginadas
style_text_dark = style_text_steel
style_text_field = style_text_card


# ---------------------------------------------------- superfícies (ttk)

def _apply_dark_surface(style: ttk.Style) -> None:
    """O chão creme e tudo que pousa direto nele."""
    style.configure(
        ".", background=GROUND, foreground=STEEL, font=FONT,
        bordercolor=STEEL_LINE, darkcolor=GROUND, lightcolor=GROUND,
        focuscolor=PEACH,
    )
    style.configure("TFrame", background=GROUND)
    style.configure("Container.TFrame", background=STEEL)
    style.configure("Steel.TFrame", background=STEEL)
    style.configure("Peach.TFrame", background=PEACH)

    style.configure("TLabel", background=GROUND, foreground=STEEL, font=FONT)
    style.configure("Dim.TLabel", background=GROUND, foreground=STEEL_SOFT, font=FONT_SMALL)
    style.configure("Title.TLabel", background=GROUND, foreground=STEEL, font=FONT_TITLE)
    style.configure("Section.TLabel", background=GROUND, foreground=STEEL, font=FONT_SECTION)
    style.configure("Error.TLabel", background=GROUND, foreground=ERROR_C, font=FONT)
    style.configure("Warning.TLabel", background=GROUND, foreground=WARNING_C, font=FONT)
    style.configure("Success.TLabel", background=GROUND, foreground=SUCCESS_C, font=FONT)
    style.configure("Mono.TLabel", background=GROUND, foreground=STEEL_SOFT, font=FONT_MONO)

    # sobre bloco steel
    style.configure("Container.TLabel", background=STEEL, foreground=ON_STEEL, font=FONT)
    style.configure("ContainerDim.TLabel", background=STEEL,
                    foreground="#A9BCC1", font=FONT_SMALL)
    style.configure("SteelTitle.TLabel", background=STEEL, foreground=PEACH, font=FONT_SECTION)
    style.configure("SteelMono.TLabel", background=STEEL, foreground="#A9BCC1", font=FONT_MONO)

    # sobre bloco peach
    style.configure("Peach.TLabel", background=PEACH, foreground=ON_PEACH, font=FONT)
    style.configure("PeachTitle.TLabel", background=PEACH, foreground=ON_PEACH, font=FONT_TITLE)

    style.configure(
        "TEntry", fieldbackground=FIELD, foreground=STEEL, insertcolor=STEEL,
        bordercolor=STEEL_LINE, borderwidth=1, relief="flat", padding=4,
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", SURFACE), ("readonly", SURFACE)],
        foreground=[("disabled", STEEL_SOFT)],
        bordercolor=[("focus", PEACH)],
    )

    style.configure(
        "TCombobox", fieldbackground=FIELD, background=FIELD, foreground=STEEL,
        arrowcolor=STEEL, bordercolor=STEEL_LINE, borderwidth=1,
        relief="flat", padding=4,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", FIELD), ("disabled", SURFACE)],
        foreground=[("readonly", STEEL), ("disabled", STEEL_SOFT)],
        background=[("readonly", FIELD)],
        bordercolor=[("focus", PEACH)],
    )

    for nome, fundo, frente in (("TCheckbutton", GROUND, STEEL),
                                ("Card.TCheckbutton", SURFACE, STEEL),
                                ("Container.TCheckbutton", STEEL, ON_STEEL)):
        style.configure(nome, background=fundo, foreground=frente, font=FONT,
                        indicatorcolor=FIELD, focuscolor=PEACH)
        style.map(nome, background=[("active", fundo)],
                  indicatorcolor=[("selected", PEACH), ("!selected", FIELD)],
                  foreground=[("disabled", STEEL_SOFT)])

    style.configure("TRadiobutton", background=GROUND, foreground=STEEL,
                    font=FONT, indicatorcolor=FIELD)
    style.map("TRadiobutton", background=[("active", GROUND)],
              indicatorcolor=[("selected", PEACH), ("!selected", FIELD)])
    style.configure("Card.TRadiobutton", background=SURFACE, foreground=STEEL,
                    font=FONT, indicatorcolor=FIELD)
    style.map("Card.TRadiobutton", background=[("active", SURFACE)],
              indicatorcolor=[("selected", PEACH), ("!selected", FIELD)])

    style.configure("TSeparator", background=STEEL_LINE)
    style.configure("Card.TSeparator", background=STEEL_LINE)

    style.configure("TScrollbar", background=STEEL_LINE, troughcolor=GROUND,
                    bordercolor=GROUND, arrowcolor=STEEL, relief="flat", borderwidth=0)
    style.map("TScrollbar", background=[("active", PEACH)])

    style.configure("TProgressbar", background=PEACH, troughcolor=SURFACE,
                    bordercolor=STEEL_LINE, lightcolor=PEACH, darkcolor=PEACH_DEEP)

    style.configure("TLabelframe", background=GROUND, bordercolor=STEEL_LINE, borderwidth=1)
    style.configure("TLabelframe.Label", background=GROUND, foreground=STEEL,
                    font=FONT_SECTION)


def _apply_card_surface(style: ttk.Style) -> None:
    """As ilhas creme claras — tudo prefixado com "Card."."""
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("CardBordered.TFrame", background=SURFACE,
                    bordercolor=STEEL_LINE, borderwidth=1, relief="solid")

    style.configure("Card.TLabel", background=SURFACE, foreground=STEEL, font=FONT)
    style.configure("CardTitle.TLabel", background=SURFACE, foreground=STEEL_DEEP,
                    font=FONT_SECTION)
    style.configure("CardDim.TLabel", background=SURFACE, foreground=STEEL_SOFT,
                    font=FONT_SMALL)
    style.configure("CardMono.TLabel", background=SURFACE, foreground=STEEL_SOFT,
                    font=FONT_MONO)
    style.configure("CardError.TLabel", background=SURFACE, foreground=ERROR_C, font=FONT)
    style.configure("CardWarning.TLabel", background=SURFACE, foreground=WARNING_C, font=FONT)
    style.configure("CardAccent.TLabel", background=SURFACE, foreground=PEACH_DEEP,
                    font=FONT_BOLD)

    style.configure("Card.TEntry", fieldbackground=FIELD, foreground=STEEL,
                    insertcolor=STEEL, bordercolor=STEEL_LINE, borderwidth=1,
                    relief="flat", padding=6)
    style.map("Card.TEntry",
              fieldbackground=[("disabled", SURFACE), ("readonly", SURFACE)],
              foreground=[("disabled", STEEL_SOFT)],
              bordercolor=[("focus", PEACH)])

    style.configure("Card.TCombobox", fieldbackground=FIELD, background=FIELD,
                    foreground=STEEL, arrowcolor=STEEL, bordercolor=STEEL_LINE,
                    borderwidth=1, relief="flat", padding=6)
    style.map("Card.TCombobox",
              fieldbackground=[("readonly", FIELD), ("disabled", SURFACE)],
              foreground=[("readonly", STEEL), ("disabled", STEEL_SOFT)],
              background=[("readonly", FIELD)],
              bordercolor=[("focus", PEACH)])

    style.configure("Card.TLabelframe", background=SURFACE, bordercolor=STEEL_LINE,
                    borderwidth=1)
    style.configure("Card.TLabelframe.Label", background=SURFACE,
                    foreground=STEEL_DEEP, font=FONT_SECTION)


def _apply_buttons(style: ttk.Style) -> None:
    """Peach é a AÇÃO; steel é o secundário; contorno é o terciário.

    O texto sobre peach é STEEL, não branco — é o par do pôster, e o
    contraste peach/branco não passaria em leitura de interface."""
    # O botão PADRÃO é contornado, não peach.
    #
    # As abas herdadas usam ttk.Button sem estilo, e são muitas por tela —
    # o Ingest tem cinco. Com o padrão em peach, a tela inteira gritava e
    # a regra "uma ação por tela" morria. Quem quer a ação principal pede
    # explicitamente Neon.TButton.
    style.configure("TButton", background=SURFACE, foreground=STEEL,
                    font=FONT_BOLD, borderwidth=1, relief="solid",
                    bordercolor=STEEL_LINE, padding=(11, 5), focuscolor=PEACH)
    style.map("TButton",
              background=[("disabled", GROUND), ("pressed", SELECT_BG_CARD),
                          ("active", FIELD)],
              bordercolor=[("active", PEACH), ("focus", PEACH)],
              foreground=[("disabled", STEEL_SOFT)])

    # a ação principal da tela — mesmo visual, nome mantido pra não
    # reescrever as chamadas existentes
    style.configure("Neon.TButton", background=PEACH, foreground=ON_PEACH,
                    font=FONT_BOLD, borderwidth=0, relief="flat", padding=(12, 6))
    style.map("Neon.TButton",
              background=[("disabled", SURFACE), ("pressed", PEACH_DEEP),
                          ("active", PEACH_SOFT)],
              foreground=[("disabled", STEEL_SOFT)])

    style.configure("Steel.TButton", background=STEEL, foreground=ON_STEEL,
                    font=FONT_BOLD, borderwidth=0, relief="flat", padding=(11, 5))
    style.map("Steel.TButton",
              background=[("disabled", SURFACE), ("pressed", STEEL_DEEP),
                          ("active", STEEL_SOFT)],
              foreground=[("disabled", STEEL_SOFT)])

    # contorno fino sobre o chão — as "pílulas" do pôster
    style.configure("Ghost.TButton", background=GROUND, foreground=STEEL,
                    font=FONT, borderwidth=1, relief="solid",
                    bordercolor=STEEL_LINE, padding=(10, 5))
    style.map("Ghost.TButton",
              background=[("active", SURFACE), ("pressed", SURFACE)],
              bordercolor=[("active", PEACH)],
              foreground=[("disabled", STEEL_SOFT)])

    # contorno claro sobre bloco steel — o Ghost usa fundo creme e sobre
    # a barra escura vira um retângulo claro, não um botão discreto
    style.configure("ContainerGhost.TButton", background=STEEL, foreground=ON_STEEL,
                    font=FONT, borderwidth=1, relief="solid",
                    bordercolor="#7A939A", padding=(11, 4))
    style.map("ContainerGhost.TButton",
              background=[("active", STEEL_DEEP), ("pressed", STEEL_DEEP)],
              foreground=[("active", PEACH)],
              bordercolor=[("active", PEACH)])

    style.configure("Card.TButton", background=PEACH, foreground=ON_PEACH,
                    font=FONT_BOLD, borderwidth=0, relief="flat", padding=(11, 5))
    style.map("Card.TButton",
              background=[("disabled", STEEL_LINE), ("pressed", PEACH_DEEP),
                          ("active", PEACH_SOFT)],
              foreground=[("disabled", STEEL_SOFT)])

    style.configure("CardGhost.TButton", background=SURFACE, foreground=STEEL,
                    font=FONT, borderwidth=1, relief="solid",
                    bordercolor=STEEL_LINE, padding=(10, 5))
    style.map("CardGhost.TButton",
              background=[("active", FIELD), ("pressed", SELECT_BG_CARD)],
              bordercolor=[("active", PEACH)],
              foreground=[("disabled", STEEL_SOFT)])

    style.configure("Danger.TButton", background=SURFACE, foreground=ERROR_C,
                    font=FONT, borderwidth=1, relief="solid",
                    bordercolor="#E0B5AC", padding=(8, 3))
    style.map("Danger.TButton", background=[("active", "#F7E2DC"),
                                            ("pressed", "#F0CFC6")])

    style.configure("Icon.TButton", background=SURFACE, foreground=STEEL,
                    font=FONT_BOLD, borderwidth=0, relief="flat", padding=(5, 2))
    style.map("Icon.TButton", background=[("active", SELECT_BG_CARD)])


def _apply_notebook(style: ttk.Style) -> None:
    """A faixa de abas é a barra de módulos do bento: pousa no chão creme,
    e a aba ativa vira um bloco steel — o mesmo gesto do pôster, em que o
    bloco selecionado ganha peso e cor."""
    # A aba selecionada muda so de COR, nunca de tamanho.
    # O `expand` que estava aqui fazia a aba ativa crescer 2px, e o
    # reflow empurrava as vizinhas: a barra inteira se remontava a cada
    # clique. Com 11 abas isso vira bagunca.
    style.configure("TNotebook", background=GROUND, bordercolor=GROUND,
                    borderwidth=0, tabmargins=(4, 5, 4, 0))
    style.configure("TNotebook.Tab", background=SURFACE, foreground=STEEL_SOFT,
                    font=FONT_SMALL, padding=(9, 5), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", STEEL), ("active", "#E2DAC6")],
              foreground=[("selected", ON_STEEL), ("active", STEEL)])

    style.configure("Sub.TNotebook", background=GROUND, borderwidth=0,
                    tabmargins=(2, 4, 2, 0))
    style.configure("Sub.TNotebook.Tab", background=GROUND, foreground=STEEL_SOFT,
                    font=FONT_SMALL, padding=(9, 4), borderwidth=0)
    style.map("Sub.TNotebook.Tab",
              background=[("selected", PEACH), ("active", SURFACE)],
              foreground=[("selected", ON_PEACH), ("active", STEEL)])


def _apply_treeview(style: ttk.Style) -> None:
    style.configure("Treeview", background=FIELD, fieldbackground=FIELD,
                    foreground=STEEL, font=FONT, bordercolor=STEEL_LINE,
                    borderwidth=0, relief="flat", rowheight=23)
    style.map("Treeview", background=[("selected", PEACH)],
              foreground=[("selected", ON_PEACH)])
    style.configure("Treeview.Heading", background=STEEL, foreground=ON_STEEL,
                    font=FONT_BOLD, relief="flat", borderwidth=0, padding=(5, 4))
    style.map("Treeview.Heading", background=[("active", STEEL_DEEP)])


# ------------------------------------------------------------- ajudantes

def card(parent, padding=CARD_PAD, bordered=True, fill=None, **kwargs):
    """Ilha arredondada do pôster.

    Devolve o Frame INTERNO, para que todo chamador antigo continue
    funcionando sem mudar uma linha:

        c = theme.card(pai)      # -> o frame interno
        c.pack(fill="x")         # -> mas pack age sobre o card externo
        ttk.Label(c, ...)        # -> e o conteúdo entra dentro

    O truque é reapontar pack/grid/place do interno para o externo. Sem
    isso, cada uma das dezenas de chamadas existentes teria de virar
    `card.body`, e o risco de esquecer uma não compensa.

    O import de widgets é local de propósito: widgets importa theme, e no
    topo isto seria import circular.
    """
    import widgets

    holder = widgets.RoundedCard(
        parent,
        fill=fill or SURFACE,
        outline=STEEL_LINE if bordered else None,
        padding=padding,
    )
    body = holder.body
    body.pack = holder.pack
    body.grid = holder.grid
    body.place = holder.place
    body.pack_forget = holder.pack_forget
    body.grid_forget = holder.grid_forget
    # quem guardar a referência consegue chegar no card externo
    body.card = holder
    return body


def section_header(parent, text, on_dark=False) -> ttk.Label:
    style_name = "Container.TLabel" if on_dark else "Section.TLabel"
    return ttk.Label(parent, text=text, style=style_name)
