"""
Widgets desenhados do CineBrain OS.

O ttk não tem canto arredondado. O pôster de referência é feito de blocos
arredondados — sem eles a identidade não existe. Então os cantos são
DESENHADOS: cada bloco é um Canvas com uma imagem de fundo gerada pelo
Pillow e um Frame comum por cima, onde entram os widgets normais.

Por que Pillow e não `Canvas.create_arc`: o Canvas do Tk não faz
antisserrilhado, e um raio de 16px sai visivelmente escadinha. O Pillow
desenha em 4× e reduz, o que dá a borda lisa do pôster. O Pillow já é
dependência do app (miniaturas e verificação de imagem), então isso não
acrescenta peso nenhum ao instalador.

CONCESSÕES DECLARADAS:
  - Recorte entrecruzado entre blocos (o "abraço" pelo canto do pôster)
    não foi implementado: exigiria que cada bloco soubesse a geometria do
    vizinho e se redesenhasse a cada mudança de tamanho. Frágil e caro
    pelo que entrega.
  - Sombra: idem. O pôster não tem sombra de verdade, só contraste de
    cor, e isso o tema já dá.

Cai de pé sem Pillow: se a importação falhar, RoundedCard vira um Frame
comum de canto reto. O app fica menos bonito e continua funcionando.
"""

import tkinter as tk
from tkinter import ttk

import theme

try:
    from PIL import Image, ImageDraw, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# fator de superamostragem: desenha grande e reduz, que é o que produz a
# borda lisa. 4 é o ponto em que o ganho visual para de compensar o custo.
_SUPERSAMPLE = 4


def _rounded_image(width, height, radius, fill, outline=None, outline_width=1):
    """Retângulo arredondado antisserrilhado, como PhotoImage do Tk."""
    if width < 2 or height < 2:
        return None
    escala = _SUPERSAMPLE
    grande = Image.new("RGBA", (width * escala, height * escala), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(grande)
    raio = min(radius, width // 2, height // 2) * escala
    caixa = [0, 0, width * escala - 1, height * escala - 1]
    # a borda e desenhada meio pixel pra dentro pra nao ser cortada pela
    # reducao — sem isso o contorno some em um dos lados
    if outline:
        desenho.rounded_rectangle(caixa, radius=raio, fill=fill,
                                  outline=outline, width=max(1, outline_width) * escala)
    else:
        desenho.rounded_rectangle(caixa, radius=raio, fill=fill)
    pequeno = grande.resize((width, height), Image.LANCZOS)
    return ImageTk.PhotoImage(pequeno)


class RoundedCard(tk.Frame):
    """Bloco arredondado. Use `.body` como pai do conteúdo.

        card = RoundedCard(pai, fill=theme.SURFACE)
        card.pack(fill="x")
        ttk.Label(card.body, text="oi", style="Card.TLabel").pack()

    `fill` define a superfície; passe o estilo ttk correspondente em
    `body_style` para que os widgets internos combinem (Card.* para creme,
    Container.* para steel, Peach.* para peach).
    """

    def __init__(self, parent, fill=None, outline=None, radius=None,
                 padding=14, body_style=None, **kwargs):
        fill = fill or theme.SURFACE
        radius = theme.RADIUS if radius is None else radius
        if body_style is None:
            body_style = {
                theme.SURFACE: "Card.TFrame",
                theme.STEEL: "Container.TFrame",
                theme.PEACH: "Peach.TFrame",
                theme.FIELD: "Card.TFrame",
            }.get(fill, "Card.TFrame")

        # o Frame externo herda a cor do PAI, não do card: é ele que
        # aparece nos quatro cantos, fora da curva
        super().__init__(parent, bd=0, highlightthickness=0, **kwargs)

        self._fill = fill
        self._outline = outline
        self._radius = radius
        self._image = None
        self._last_size = (0, 0)

        if not PIL_AVAILABLE:
            # sem Pillow: canto reto, mesma cor, mesmo layout
            self.configure(bg=fill)
            self.body = ttk.Frame(self, style=body_style, padding=padding)
            self.body.pack(fill="both", expand=True)
            self._canvas = None
            return

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._image_id = self._canvas.create_image(0, 0, anchor="nw")

        self.body = ttk.Frame(self._canvas, style=body_style, padding=padding)
        self._body_id = self._canvas.create_window(0, 0, window=self.body, anchor="nw")

        self._sync_parent_bg(parent)
        self._canvas.bind("<Configure>", self._on_resize)
        # o card acompanha a altura natural do conteúdo
        self.body.bind("<Configure>", self._on_body_resize)

    # ------------------------------------------------------------ interno

    def _sync_parent_bg(self, parent):
        """O canvas precisa ter a cor do que está ATRÁS do card, senão os
        cantos arredondados mostram um quadrado de cor errada."""
        cor = theme.GROUND
        try:
            estilo = parent.cget("style") if hasattr(parent, "cget") else ""
            mapa = {
                "Card.TFrame": theme.SURFACE,
                "CardBordered.TFrame": theme.SURFACE,
                "Container.TFrame": theme.STEEL,
                "Steel.TFrame": theme.STEEL,
                "Peach.TFrame": theme.PEACH,
            }
            cor = mapa.get(estilo, theme.GROUND)
        except tk.TclError:
            pass
        try:
            if isinstance(parent, tk.Canvas):
                cor = parent.cget("bg")
        except tk.TclError:
            pass
        self._canvas.configure(bg=cor)
        self.configure(bg=cor)

    def _on_body_resize(self, event):
        altura = event.height
        if altura > 1 and self._canvas is not None:
            self._canvas.configure(height=altura)

    def _on_resize(self, event):
        largura, altura = event.width, event.height
        if largura < 2 or altura < 2:
            return
        if (largura, altura) == self._last_size:
            return
        self._last_size = (largura, altura)
        self._redraw(largura, altura)
        self._canvas.itemconfigure(self._body_id, width=largura)

    def _redraw(self, largura, altura):
        imagem = _rounded_image(largura, altura, self._radius,
                                self._fill, self._outline)
        if imagem is None:
            return
        # a referência precisa sobreviver: PhotoImage some se coletado
        self._image = imagem
        self._canvas.itemconfigure(self._image_id, image=imagem)

    # ------------------------------------------------------------ público

    def set_fill(self, fill):
        self._fill = fill
        if self._canvas is None:
            self.configure(bg=fill)
            return
        largura, altura = self._last_size
        if largura and altura:
            self._redraw(largura, altura)


class Pill(tk.Canvas):
    """A pílula contornada do pôster — legenda que flutua sobre o bloco.

    Usada para rótulos curtos: "PRÉ-PRODUÇÃO", "62%", "3 PENDÊNCIAS".
    """

    def __init__(self, parent, text, fill=None, text_color=None,
                 outline=None, font=None, padding=(12, 5), **kwargs):
        fill = fill if fill is not None else ""
        text_color = text_color or theme.STEEL
        outline = outline or theme.STEEL_LINE
        font = font or theme.FONT_SMALL

        temporario = tk.Canvas(parent)
        largura_texto = temporario.winfo_reqwidth()
        temporario.destroy()

        super().__init__(parent, highlightthickness=0, bd=0, **kwargs)
        self._text = text
        self._fill = fill
        self._outline = outline
        self._text_color = text_color
        self._font = font
        self._padding = padding
        self._image = None

        self._text_id = self.create_text(0, 0, text=text, fill=text_color,
                                         font=font, anchor="nw")
        caixa = self.bbox(self._text_id)
        largura = (caixa[2] - caixa[0]) + padding[0] * 2
        altura = (caixa[3] - caixa[1]) + padding[1] * 2
        self.configure(width=largura, height=altura)
        self._sync_bg(parent)

        if PIL_AVAILABLE:
            self._image = _rounded_image(
                largura, altura, altura // 2,
                fill if fill else self.cget("bg"),
                outline=outline, outline_width=1,
            )
            fundo = self.create_image(0, 0, anchor="nw", image=self._image)
            self.tag_lower(fundo, self._text_id)
        self.coords(self._text_id, padding[0], padding[1])

    def _sync_bg(self, parent):
        cor = theme.GROUND
        try:
            estilo = parent.cget("style") if hasattr(parent, "cget") else ""
            cor = {
                "Card.TFrame": theme.SURFACE,
                "CardBordered.TFrame": theme.SURFACE,
                "Container.TFrame": theme.STEEL,
                "Steel.TFrame": theme.STEEL,
                "Peach.TFrame": theme.PEACH,
            }.get(estilo, theme.GROUND)
        except tk.TclError:
            pass
        self.configure(bg=cor)

    def set_text(self, text):
        self.itemconfigure(self._text_id, text=text)


def arrow_badge(parent, direction="ne", size=38, fill=None, arrow_color=None):
    """O badge quadrado com seta que o pôster solta no canto dos blocos."""
    fill = fill or theme.PEACH
    arrow_color = arrow_color or theme.STEEL
    setas = {"ne": "↗", "nw": "↖", "se": "↘", "sw": "↙"}
    card = RoundedCard(parent, fill=fill, radius=12, padding=0)
    card.configure(width=size, height=size)
    ttk.Label(
        card.body, text=setas.get(direction, "↗"),
        background=fill, foreground=arrow_color,
        font=(theme.FONT_FAMILY_UI, int(size * 0.42), "bold"),
    ).pack(expand=True)
    return card
