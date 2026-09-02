"""
Aba "Metadados": preenchimento de metadados IPTC/XMP de uma foto por vez,
mais o modo de lote seletivo por campo ("Processar em lote...").

Fluxo:
1. Você edita a foto normalmente no seu editor de sempre.
2. Abre a foto aqui (botão, ou arrasta o arquivo pra aba).
3. O app mostra os metadados já existentes (se houver) pra você revisar.
4. Você preenche/edita os campos. A Data (e o GPS, se houver) são sempre
   lidos da câmera (EXIF) e não são editáveis aqui.
5. Antes de salvar, o app confere se o perfil de validação ativo foi
   atendido. Se faltar algo, avisa e permite corrigir ou salvar mesmo assim.
6. Salva os metadados sobre o próprio arquivo. A imagem em si (pixels)
   nunca é alterada — só os metadados.
"""

import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import clipboard_engine as ce
import theme
import fileinfo_engine as fi
import resize_engine as rz
from metadata_engine import (
    ALL_FIELD_KEYS,
    DIGITAL_SOURCES,
    KEYWORD_LIMITS,
    KEYWORD_SOFT_LIMIT,
    PROPERTY_RELEASE_STATUSES,
    RELEASE_STATUSES,
    BATCH_DEFAULT_CHECKED,
    DEFAULT_PROFILE,
    ExifToolNotFound,
    FIELD_LABELS,
    MetadataWriteError,
    PhotoFields,
    check_exiftool,
    get_camera_datetime,
    get_gps_string,
    get_profile,
    get_shorter_edge,
    list_image_files,
    list_profiles,
    load_prefs,
    read_existing_fields,
    save_prefs,
    validate,
    write_batch_log_csv,
    write_metadata,
    write_metadata_batch,
)
from ui_common import CustomFieldsEditor, DND_AVAILABLE, DND_FILES, bind_mousewheel, extract_dropped_paths, show_issues_dialog

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


THUMB_MAX = 360
STICKY_FIELD_KEYS = [
    "creator", "creator_url", "sublocation", "city", "state", "country",
    "country_code", "copyright", "credit", "source", "usage_terms",
]


class MetadataTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=0)

        self.prefs = load_prefs()

        self.current_path = None
        self.current_fields = PhotoFields()
        self.clipboard = ce.Clipboard()
        self.clipboard.load()
        self.current_shorter_edge = None
        self.thumb_imgtk = None  # precisa manter referência

        self._profile_labels = dict(list_profiles())
        self._profile_keys_by_label = {v: k for k, v in self._profile_labels.items()}
        self.active_profile_key = self.prefs.get("profile") or DEFAULT_PROFILE
        if self.active_profile_key not in self._profile_labels:
            self.active_profile_key = DEFAULT_PROFILE

        self._build_ui()
        self._set_photo_fields_enabled(False)
        self._apply_prefs_to_sticky_fields()
        self._on_profile_change()

        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop_photo)

        if not check_exiftool():
            messagebox.showwarning(
                "ExifTool não encontrado",
                "O ExifTool não foi encontrado.\n\n"
                "Instale em https://exiftool.org antes de usar o app "
                "(Mac: 'brew install exiftool' / Windows: instalador oficial).",
            )

    def on_app_close(self):
        """Chamado pela janela raiz antes de fechar — persiste os campos
        'de casa' mesmo que o usuário nunca tenha clicado em Salvar."""
        save_prefs(self._current_sticky_prefs())

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Button(top, text="Abrir foto...", command=self.on_open).pack(side="left")
        self.path_label = ttk.Label(top, text="Nenhuma foto aberta (ou arraste um arquivo pra cá)", foreground=theme.FG_DIM)
        self.path_label.pack(side="left", padx=10)

        profile_frame = ttk.Frame(top)
        profile_frame.pack(side="right")
        ttk.Label(profile_frame, text="Perfil de validação:").pack(side="left", padx=(0, 5))
        self.profile_var = tk.StringVar(value=self._profile_labels[self.active_profile_key])
        profile_combo = ttk.Combobox(
            profile_frame, textvariable=self.profile_var, state="readonly",
            values=list(self._profile_labels.values()), width=26,
        )
        profile_combo.pack(side="left")
        profile_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_profile_change())

        # AÇÕES PRIMEIRO, presas ao rodapé da janela.
        # Precisam ser empacotadas ANTES da área rolável: o pack do Tk dá
        # o espaço restante a quem vem depois, então uma barra criada
        # depois de um `expand=True` fica espremida a quase-zero.
        # E fora da rolagem, para que Salvar não desapareça ao rolar.
        acoes = ttk.Frame(self, padding=(10, 8))
        acoes.pack(side="bottom", fill="x")
        self.keep_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            acoes, text="Manter cópia de segurança (_original)",
            variable=self.keep_backup_var,
        ).pack(side="left")
        ttk.Button(acoes, text="Processar em lote...",
                   command=self.on_open_batch).pack(side="right", padx=(0, 8))
        ttk.Button(acoes, text="Salvar metadados", style="Neon.TButton",
                   command=self.on_save).pack(side="right")
        self.status_label = ttk.Label(acoes, text="", foreground=theme.SUCCESS)
        self.status_label.pack(side="left", padx=(16, 0))

        # ÁREA ROLÁVEL — o formulário cresceu além da altura da janela com
        # os campos de banco de imagens e o redimensionador, e sem isto o
        # conteúdo de baixo ficava inalcançável.
        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True)
        canvas = tk.Canvas(holder, highlightthickness=0)
        vbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas, padding=10)
        body.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
        self._form_canvas = canvas
        self._form_body = body

        # coluna esquerda: miniatura + dados só-leitura da câmera
        left = ttk.Frame(body, width=THUMB_MAX)
        left.pack(side="left", fill="y", padx=(0, 15))
        self.thumb_label = ttk.Label(left, text="(sem preview)", relief="groove", anchor="center")
        self.thumb_label.pack()
        # A data passa a ser EDITÁVEL. Câmera com data errada, foto
        # escaneada e material de arquivo são casos reais em que a data da
        # captura precisa ser corrigida à mão. Vazio = mantém a da câmera.
        ttk.Label(left, text="Data criada (AAAA-MM-DD HH:MM):").pack(anchor="w", pady=(6, 0))
        self.date_entry = ttk.Entry(left)
        self.date_entry.pack(fill="x")
        ttk.Label(left, text="Deixe em branco para manter a data da câmera.",
                  style="Dim.TLabel", wraplength=THUMB_MAX, justify="left"
                  ).pack(anchor="w")
        # Aviso do perfil sobre o tamanho. Separado da ficha porque é
        # julgamento, não dado: a ficha diz o que a foto É, isto diz se
        # ela serve pro perfil ativo.
        self.res_label = ttk.Label(left, text="", wraplength=THUMB_MAX, justify="left")
        self.res_label.pack(pady=(8, 0), anchor="w")

        # FICHA TÉCNICA — tudo o que o arquivo sabe sobre si, agrupado.
        # Substitui os rótulos avulsos de data e GPS que havia aqui.
        ttk.Label(left, text="Ficha técnica", style="Section.TLabel").pack(
            anchor="w", pady=(12, 2))
        self.info_frame = ttk.Frame(left)
        self.info_frame.pack(fill="x")
        self._render_fileinfo([])

        # coluna direita: campos
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self.caption_label = ttk.Label(right, text="Legenda/Descrição:")
        self.caption_label.pack(anchor="w")
        self.caption_text = tk.Text(right, height=3, wrap="word")
        self.caption_text.pack(fill="x")
        self.caption_text.bind("<KeyRelease>", self._update_caption_counter)
        self.caption_counter = ttk.Label(right, text="")
        self.caption_counter.pack(anchor="e")

        ttk.Label(right, text="Título (Headline) — opcional:").pack(anchor="w", pady=(10, 0))
        self.headline_entry = ttk.Entry(right)
        self.headline_entry.pack(fill="x")

        ttk.Label(
            right, text="Descrição ampliada (sem limite de tamanho) — opcional:"
        ).pack(anchor="w", pady=(10, 0))
        self.instructions_text = tk.Text(right, height=4, wrap="word")
        self.instructions_text.pack(fill="x")

        kw_head = ttk.Frame(right)
        kw_head.pack(fill="x", pady=(10, 0))
        ttk.Label(kw_head, text="Palavras-chave / tags (separadas por vírgula):").pack(side="left")
        # Adobe aceita 49 e Shutterstock 50; passar disso trunca ou
        # reprova o envio. Melhor saber aqui que na rejeição.
        self.keywords_counter = ttk.Label(kw_head, text="", style="Dim.TLabel")
        self.keywords_counter.pack(side="right")
        self.keywords_entry = ttk.Entry(right)
        self.keywords_entry.bind("<KeyRelease>", self._update_keywords_counter)
        self.keywords_entry.pack(fill="x")

        creator_frame = ttk.Frame(right)
        creator_frame.pack(fill="x", pady=(10, 0))
        creator_col = ttk.Frame(creator_frame)
        creator_col.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(creator_col, text="Criador (fotógrafo/autor):").pack(anchor="w")
        self.creator_entry = ttk.Entry(creator_col)
        self.creator_entry.pack(fill="x")
        creator_url_col = ttk.Frame(creator_frame)
        creator_url_col.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Label(creator_url_col, text="Site/contato do criador (opcional):").pack(anchor="w")
        self.creator_url_entry = ttk.Entry(creator_url_col)
        self.creator_url_entry.pack(fill="x")

        # Local (Sub-location IPTC): o lugar ESPECÍFICO dentro da cidade.
        # Ganha linha inteira porque o texto costuma ser longo.
        subloc_frame = ttk.Frame(right)
        subloc_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(subloc_frame,
                  text="Local (dentro da cidade — ex.: Praia de Copacabana, Teatro Municipal):"
                  ).pack(anchor="w")
        self.sublocation_entry = ttk.Entry(subloc_frame)
        self.sublocation_entry.pack(fill="x")

        loc_frame = ttk.Frame(right)
        loc_frame.pack(fill="x", pady=(6, 0))
        col1 = ttk.Frame(loc_frame)
        col1.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(col1, text="Cidade:").pack(anchor="w")
        self.city_entry = ttk.Entry(col1)
        self.city_entry.pack(fill="x")
        col2 = ttk.Frame(loc_frame)
        col2.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(col2, text="Estado/Província:").pack(anchor="w")
        self.state_entry = ttk.Entry(col2)
        self.state_entry.pack(fill="x")
        col3 = ttk.Frame(loc_frame)
        col3.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(col3, text="País:").pack(anchor="w")
        self.country_entry = ttk.Entry(col3)
        self.country_entry.pack(fill="x")
        col4 = ttk.Frame(loc_frame)
        col4.pack(side="left", padx=(5, 0))
        ttk.Label(col4, text="Cód. ISO:").pack(anchor="w")
        self.country_code_entry = ttk.Entry(col4, width=8)
        self.country_code_entry.pack()

        rights_frame1 = ttk.Frame(right)
        rights_frame1.pack(fill="x", pady=(10, 0))
        cr_col = ttk.Frame(rights_frame1)
        cr_col.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(cr_col, text="Copyright (opcional):").pack(anchor="w")
        self.copyright_entry = ttk.Entry(cr_col)
        self.copyright_entry.pack(fill="x")
        credit_col = ttk.Frame(rights_frame1)
        credit_col.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Label(credit_col, text="Crédito (opcional):").pack(anchor="w")
        self.credit_entry = ttk.Entry(credit_col)
        self.credit_entry.pack(fill="x")

        rights_frame2 = ttk.Frame(right)
        rights_frame2.pack(fill="x", pady=(10, 0))
        source_col = ttk.Frame(rights_frame2)
        source_col.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(source_col, text="Fonte (opcional):").pack(anchor="w")
        self.source_entry = ttk.Entry(source_col)
        self.source_entry.pack(fill="x")
        usage_col = ttk.Frame(rights_frame2)
        usage_col.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Label(usage_col, text="Termos de uso/Licença (opcional):").pack(anchor="w")
        self.usage_terms_entry = ttk.Entry(usage_col)
        self.usage_terms_entry.pack(fill="x")

        # ------------------------------------------- banco de imagens
        ttk.Separator(right).pack(fill="x", pady=(14, 0))
        ttk.Label(right, text="Banco de imagens", style="Section.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(
            right,
            text="Campos que as agências passaram a exigir. Sem a declaração de "
                 "origem, envios com IA são recusados; sem status de liberação, "
                 "foto com pessoa reconhecível também.",
            style="Dim.TLabel", wraplength=640, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        ttk.Label(right, text="Título de venda (curto — é o que aparece na busca):").pack(anchor="w")
        self.object_name_entry = ttk.Entry(right)
        self.object_name_entry.pack(fill="x")

        ttk.Label(right, text="Texto alternativo (acessibilidade — descreva a imagem em uma frase):").pack(anchor="w", pady=(8, 0))
        self.alt_text_entry = ttk.Entry(right)
        self.alt_text_entry.pack(fill="x")

        ttk.Label(right, text="Descrição estendida (acessibilidade — opcional):").pack(anchor="w", pady=(8, 0))
        self.ext_descr_text = tk.Text(right, height=2, wrap="word")
        theme.style_text_card(self.ext_descr_text)
        self.ext_descr_text.pack(fill="x")

        origem_frame = ttk.Frame(right)
        origem_frame.pack(fill="x", pady=(8, 0))
        col_a = ttk.Frame(origem_frame)
        col_a.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(col_a, text="Origem digital (declaração de IA):").pack(anchor="w")
        self._digital_labels = [rot for _iri, rot in DIGITAL_SOURCES]
        self._digital_map = {rot: iri for iri, rot in DIGITAL_SOURCES}
        self.digital_source_var = tk.StringVar(value=self._digital_labels[0])
        ttk.Combobox(col_a, textvariable=self.digital_source_var, state="readonly",
                     values=self._digital_labels).pack(fill="x")

        rel_frame = ttk.Frame(right)
        rel_frame.pack(fill="x", pady=(8, 0))
        col_b = ttk.Frame(rel_frame)
        col_b.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(col_b, text="Liberação de modelo:").pack(anchor="w")
        self._model_labels = [rot for _v, rot in RELEASE_STATUSES]
        self._model_map = {rot: v for v, rot in RELEASE_STATUSES}
        self.model_release_var = tk.StringVar(value=self._model_labels[0])
        ttk.Combobox(col_b, textvariable=self.model_release_var, state="readonly",
                     values=self._model_labels).pack(fill="x")
        col_c = ttk.Frame(rel_frame)
        col_c.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Label(col_c, text="Liberação de propriedade:").pack(anchor="w")
        self._prop_labels = [rot for _v, rot in PROPERTY_RELEASE_STATUSES]
        self._prop_map = {rot: v for v, rot in PROPERTY_RELEASE_STATUSES}
        self.property_release_var = tk.StringVar(value=self._prop_labels[0])
        ttk.Combobox(col_c, textvariable=self.property_release_var, state="readonly",
                     values=self._prop_labels).pack(fill="x")

        ttk.Separator(right).pack(fill="x", pady=(14, 0))
        self._build_resize_section(right)

        self.custom_editor = CustomFieldsEditor(
            right,
            "Grava qualquer tag do ExifTool além do padrãozinho acima (ex.: \"XMP:Rating\", "
            "\"IPTC:Urgency\"). Vale só pra esta foto/gravação — some ao abrir outra foto.",
        )
        self.custom_editor.pack(fill="x", pady=(12, 0))

        # roda do mouse em qualquer ponto do formulário, com a convenção
        # de cada sistema operacional
        bind_mousewheel(canvas, body)

        # ------------------------------------ área de transferência
        # O gesto que isto serve: você acabou de etiquetar uma foto e a
        # próxima é do mesmo trabalho. Copiar e colar evita redigitar
        # autor, cidade, direitos e metade da legenda.
        clip = theme.card(right)
        clip.pack(fill="x", pady=(14, 0))
        linha = ttk.Frame(clip, style="Card.TFrame")
        linha.pack(fill="x")
        ttk.Label(linha, text="Área de transferência de metadados",
                  style="CardTitle.TLabel").pack(side="left")
        ttk.Button(linha, text="limpar", style="Icon.TButton",
                   command=self.on_clear_clipboard).pack(side="right")

        self.clip_label = ttk.Label(clip, text="", style="CardDim.TLabel",
                                    wraplength=520, justify="left")
        self.clip_label.pack(anchor="w", pady=(2, 8))

        botoes_clip = ttk.Frame(clip, style="Card.TFrame")
        botoes_clip.pack(fill="x")
        ttk.Button(botoes_clip, text="Copiar desta foto", style="Card.TButton",
                   command=self.on_copy_metadata).pack(side="left")
        ttk.Button(botoes_clip, text="Colar aqui", style="CardGhost.TButton",
                   command=self.on_paste_metadata).pack(side="left", padx=6)
        ttk.Button(botoes_clip, text="Copiar de outra foto…", style="CardGhost.TButton",
                   command=self.on_copy_from_file).pack(side="left")
        self._refresh_clipboard_label()


        if not DND_AVAILABLE:
            ttk.Label(
                right,
                text="(arrastar-e-soltar indisponível nesta instalação — use o botão \"Abrir foto...\")",
                foreground=theme.FG_DIM,
            ).pack(anchor="w")

    def _sticky_widgets(self):
        return {
            "creator": self.creator_entry,
            "creator_url": self.creator_url_entry,
            "sublocation": self.sublocation_entry,
            "city": self.city_entry,
            "state": self.state_entry,
            "country": self.country_entry,
            "country_code": self.country_code_entry,
            "copyright": self.copyright_entry,
            "credit": self.credit_entry,
            "source": self.source_entry,
            "usage_terms": self.usage_terms_entry,
        }

    def _apply_prefs_to_sticky_fields(self):
        widgets = self._sticky_widgets()
        for key in STICKY_FIELD_KEYS:
            value = self.prefs.get(key, "")
            if value:
                widgets[key].delete(0, "end")
                widgets[key].insert(0, value)

    def _current_sticky_prefs(self) -> dict:
        widgets = self._sticky_widgets()
        prefs = {key: widgets[key].get().strip() for key in STICKY_FIELD_KEYS}
        prefs["profile"] = self.active_profile_key
        return prefs

    def _on_profile_change(self):
        # o limite de tags muda com o perfil; o contador precisa
        # acompanhar em vez de mostrar o número do perfil anterior
        self.after(1, self._update_keywords_counter)
        label = self.profile_var.get()
        self.active_profile_key = self._profile_keys_by_label.get(label, DEFAULT_PROFILE)
        profile = get_profile(self.active_profile_key)
        max_len = profile["caption_max_len"]
        forbidden = profile["forbidden_chars"]
        if max_len:
            hint = f" (máx. {max_len} caracteres"
            if forbidden:
                hint += ", sem " + "/".join({"\"": "aspas", "'": "apóstrofo", ",": "vírgula", "(": "parênteses", ")": "parênteses"}.get(c, c) for c in forbidden)
            hint += ")"
        else:
            hint = " (sem limite de caracteres neste perfil)"
        self.caption_label.configure(text="Legenda/Descrição:" + hint)
        self._update_caption_counter()

    def _on_drop_photo(self, event):
        paths = extract_dropped_paths(event)
        if not paths:
            return
        path = paths[0]
        if os.path.isdir(path):
            files = list_image_files(path)
            if not files:
                messagebox.showinfo("Pasta sem fotos", "Não encontrei fotos suportadas nessa pasta.\n\nDica: pra processar várias fotos de uma vez, use \"Processar em lote...\".")
                return
            path = files[0]
        self._open_photo(path)

    def _set_photo_fields_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for w in (self.caption_text, self.instructions_text):
            w.configure(state=state)
        for w in (self.headline_entry, self.keywords_entry):
            w.configure(state=state)

    def _update_caption_counter(self, _event=None):
        text = self.caption_text.get("1.0", "end-1c")
        n = len(text)
        max_len = get_profile(self.active_profile_key)["caption_max_len"]
        if max_len:
            self.caption_counter.configure(text=f"{n} / {max_len}")
            self.caption_counter.configure(foreground=theme.ERROR if n > max_len else theme.FG)
        else:
            self.caption_counter.configure(text=f"{n} caracteres", foreground=theme.FG)

    # -------------------------------------------------------------- ações
    def on_open(self):
        path = filedialog.askopenfilename(
            title="Escolha a foto",
            filetypes=[("Imagens", "*.jpg *.jpeg *.tif *.tiff *.png"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        self._open_photo(path)

    def _open_photo(self, path: str):
        try:
            existing = read_existing_fields(path)
            camera_dt = get_camera_datetime(path)
            shorter_edge = get_shorter_edge(path)
            gps = get_gps_string(path)
        except ExifToolNotFound as e:
            messagebox.showerror("ExifTool não encontrado", str(e))
            return
        except MetadataWriteError as e:
            messagebox.showerror("Erro ao ler metadados", str(e))
            return

        # a data é sempre a da câmera, nunca a que porventura já esteja no IPTC
        existing.date_created = camera_dt

        self.current_path = path
        self.current_fields = existing
        self.current_shorter_edge = shorter_edge

        self.path_label.configure(text=os.path.basename(path))
        self._set_photo_fields_enabled(True)
        self._fill_form(existing)
        self._set_date_entry(existing.date_created)
        self._update_resize_label()
        # a ficha é lida do arquivo, então só faz sentido depois de abrir
        self._refresh_fileinfo()
        self._update_side_labels(camera_dt, shorter_edge, gps)
        self._load_thumbnail(path)
        self.custom_editor.clear()  # campos avançados são específicos de cada gravação
        self.status_label.configure(text="")

    def _fill_form(self, fields: PhotoFields):
        self.caption_text.delete("1.0", "end")
        self.caption_text.insert("1.0", fields.caption)
        self._update_caption_counter()

        self.headline_entry.delete(0, "end")
        self.headline_entry.insert(0, fields.headline)

        self.instructions_text.delete("1.0", "end")
        self.instructions_text.insert("1.0", fields.instructions)

        self.keywords_entry.delete(0, "end")
        self.keywords_entry.insert(0, fields.keywords_as_text())

        # campos "de casa" (autor/local/direitos): só sobrescreve se o
        # arquivo já tinha algo; senão mantém o que estiver digitado —
        # já vem pré-preenchido pelas preferências salvas da última sessão
        widgets = self._sticky_widgets()
        for key in STICKY_FIELD_KEYS:
            value = getattr(fields, key, "")
            if value:
                widgets[key].delete(0, "end")
                widgets[key].insert(0, value)
        self._fill_agency_fields(fields)
        self._update_keywords_counter()

    # ------------------------------------------ redimensionamento

    def _build_resize_section(self, parent):
        """Painel de redimensionamento.

        É o único lugar do app que reescreve pixels — tudo o mais mexe só
        nos metadados e deixa a imagem byte a byte idêntica. Por isso o
        padrão é gravar uma CÓPIA: recodificar por cima do original é
        irreversível."""
        ttk.Label(parent, text="Redimensionar", style="Section.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(
            parent,
            text="Recodifica a imagem — por isso grava uma cópia por padrão. Os "
                 "metadados são copiados para o arquivo novo.",
            style="Dim.TLabel", wraplength=640, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        linha = ttk.Frame(parent)
        linha.pack(fill="x")

        col_l = ttk.Frame(linha)
        col_l.pack(side="left")
        ttk.Label(col_l, text="Largura:").pack(anchor="w")
        self.resize_w = ttk.Entry(col_l, width=8)
        self.resize_w.pack()

        # o cadeado: fechado mantém a proporção
        self.keep_ratio_var = tk.BooleanVar(value=True)
        col_lock = ttk.Frame(linha)
        col_lock.pack(side="left", padx=8)
        ttk.Label(col_lock, text=" ").pack(anchor="w")
        self.lock_button = ttk.Button(col_lock, text="🔒", width=3,
                                      command=self._toggle_ratio_lock)
        self.lock_button.pack()

        col_a = ttk.Frame(linha)
        col_a.pack(side="left")
        ttk.Label(col_a, text="Altura:").pack(anchor="w")
        self.resize_h = ttk.Entry(col_a, width=8)
        self.resize_h.pack()

        col_q = ttk.Frame(linha)
        col_q.pack(side="left", padx=(14, 0))
        ttk.Label(col_q, text="Qualidade JPEG:").pack(anchor="w")
        self.resize_q = ttk.Entry(col_q, width=5)
        self.resize_q.insert(0, str(rz.DEFAULT_QUALITY))
        self.resize_q.pack()

        # com o cadeado fechado, digitar num campo calcula o outro
        self.resize_w.bind("<KeyRelease>", lambda _e: self._sync_ratio("w"))
        self.resize_h.bind("<KeyRelease>", lambda _e: self._sync_ratio("h"))

        self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent, text="Sobrescrever o original (não dá pra desfazer)",
            variable=self.overwrite_var,
        ).pack(anchor="w", pady=(6, 0))

        acoes = ttk.Frame(parent)
        acoes.pack(fill="x", pady=(6, 0))
        # Os atalhos de tamanho só PREENCHEM o campo; quem aplica é o
        # botão de ação. Ele fica em steel para ter peso próprio sem
        # competir com o Salvar metadados, que é a ação da tela.
        ttk.Label(acoes, text="atalhos:", style="Dim.TLabel").pack(side="left", padx=(0, 6))
        for rotulo, largura in (("2000px", 2000), ("3000px", 3000), ("4000px", 4000)):
            ttk.Button(acoes, text=rotulo, width=7,
                       command=lambda w=largura: self._preset_resize(w)).pack(side="left", padx=(0, 4))
        ttk.Button(acoes, text="Aplicar redimensionamento", style="Steel.TButton",
                   command=self.on_resize).pack(side="right")

        self.resize_label = ttk.Label(parent, text="", style="Dim.TLabel",
                                      wraplength=640, justify="left")
        self.resize_label.pack(anchor="w", pady=(4, 0))

    def _toggle_ratio_lock(self):
        self.keep_ratio_var.set(not self.keep_ratio_var.get())
        self.lock_button.configure(text="🔒" if self.keep_ratio_var.get() else "🔓")
        self._update_resize_label()

    def _preset_resize(self, largura):
        self.resize_w.delete(0, "end")
        self.resize_w.insert(0, str(largura))
        self._sync_ratio("w")

    def _sync_ratio(self, origem):
        """Com o cadeado fechado, o lado digitado calcula o outro."""
        if not self.keep_ratio_var.get() or not self.current_path:
            self._update_resize_label()
            return
        tamanho = rz.get_size(self.current_path)
        if not tamanho:
            return
        lo, ao = tamanho
        try:
            if origem == "w":
                valor = int(self.resize_w.get().strip() or 0)
                if valor > 0:
                    self.resize_h.delete(0, "end")
                    self.resize_h.insert(0, str(max(1, round(valor * ao / lo))))
            else:
                valor = int(self.resize_h.get().strip() or 0)
                if valor > 0:
                    self.resize_w.delete(0, "end")
                    self.resize_w.insert(0, str(max(1, round(valor * lo / ao))))
        except ValueError:
            pass
        self._update_resize_label()

    def _update_resize_label(self):
        if not self.current_path:
            self.resize_label.configure(text="Abra uma foto para redimensionar.")
            return
        tamanho = rz.get_size(self.current_path)
        if not tamanho:
            self.resize_label.configure(text="")
            return
        cadeado = "proporção travada" if self.keep_ratio_var.get() else "proporção livre"
        self.resize_label.configure(text="Original: %d × %d px · %s" % (tamanho[0], tamanho[1], cadeado))

    def _form_differs_from_file(self):
        """Há metadado digitado que ainda não está no arquivo?

        Compara o formulário com o que está gravado. Importa aqui porque
        o redimensionamento copia os metadados DO ARQUIVO — o que só
        existe na tela seria perdido na cópia sem o usuário perceber."""
        if not self.current_path:
            return False
        try:
            no_arquivo = read_existing_fields(self.current_path)
        except Exception:
            return False
        na_tela = self._collect_fields()
        for chave in ALL_FIELD_KEYS:
            atual = getattr(na_tela, chave, None)
            gravado = getattr(no_arquivo, chave, None)
            if chave == "keywords":
                if list(atual or []) != list(gravado or []):
                    return True
            elif (atual or "").strip() != (gravado or "").strip():
                return True
        return bool(self.custom_editor.collect())

    def _ask_metadata_choice(self):
        """Pergunta o que fazer com os metadados ainda não salvos.

        Diálogo próprio em vez de askyesnocancel: "Sim/Não/Cancelar" não
        diz o que cada opção faz, e a escolha aqui altera o arquivo."""
        janela = tk.Toplevel(self)
        janela.title("Metadados não salvos")
        janela.configure(bg=theme.BG_APP)
        janela.transient(self)
        janela.grab_set()
        escolha = {"valor": None}

        card = theme.card(janela, padding=16)
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(card, text="Você preencheu metadados que ainda não foram salvos",
                  style="CardTitle.TLabel", wraplength=430, justify="left").pack(anchor="w")
        ttk.Label(
            card,
            text="O redimensionamento copia os metadados que estão gravados no "
                 "arquivo. O que está só na tela se perderia.",
            style="Card.TLabel", wraplength=430, justify="left",
        ).pack(anchor="w", pady=(6, 12))

        def responder(valor):
            escolha["valor"] = valor
            janela.destroy()

        ttk.Button(card, text="Gravar os metadados e redimensionar",
                   style="Card.TButton",
                   command=lambda: responder("aplicar")).pack(fill="x")
        ttk.Label(card, text="Salva o que você digitou e leva tudo para a imagem nova.",
                  style="CardDim.TLabel", wraplength=430, justify="left").pack(anchor="w", pady=(2, 8))

        ttk.Button(card, text="Redimensionar sem gravar",
                   style="CardGhost.TButton",
                   command=lambda: responder("ignorar")).pack(fill="x")
        ttk.Label(card, text="A imagem nova leva só os metadados que já estavam no arquivo.",
                  style="CardDim.TLabel", wraplength=430, justify="left").pack(anchor="w", pady=(2, 8))

        ttk.Button(card, text="Cancelar", style="CardGhost.TButton",
                   command=lambda: responder(None)).pack(fill="x")

        janela.protocol("WM_DELETE_WINDOW", lambda: responder(None))
        self.wait_window(janela)
        return escolha["valor"]

    def on_resize(self):
        if not self.current_path:
            messagebox.showinfo("Nenhuma foto aberta", "Abra uma foto primeiro.")
            return
        try:
            largura = int(self.resize_w.get().strip() or 0) or None
            altura = int(self.resize_h.get().strip() or 0) or None
            qualidade = int(self.resize_q.get().strip() or rz.DEFAULT_QUALITY)
        except ValueError:
            messagebox.showinfo("Valores inválidos",
                                "Largura, altura e qualidade precisam ser números.")
            return
        if not largura and not altura:
            messagebox.showinfo("Falta o tamanho",
                                "Informe a largura, a altura, ou as duas.")
            return

        # Metadados digitados e não salvos se perderiam na cópia — o
        # redimensionamento copia do ARQUIVO, não da tela.
        gravar_antes = False
        if self._form_differs_from_file():
            escolha = self._ask_metadata_choice()
            if escolha is None:
                return
            gravar_antes = (escolha == "aplicar")

        sobrescrever = bool(self.overwrite_var.get())
        if sobrescrever and not messagebox.askyesno(
            "Sobrescrever o original?",
            "Isto recodifica o arquivo original — não dá pra desfazer, e "
            "recodificar sempre perde alguma qualidade.\n\nContinuar?"):
            return

        # grava ANTES de redimensionar: assim o -tagsFromFile do
        # ExifTool já encontra os metadados novos no original
        if gravar_antes:
            try:
                write_metadata(self.current_path, self._collect_fields(),
                               keep_backup=self.keep_backup_var.get(),
                               custom_fields=self.custom_editor.collect())
                save_prefs(self._current_sticky_prefs())
            except (ExifToolNotFound, MetadataWriteError) as e:
                messagebox.showerror("Não consegui gravar os metadados", str(e))
                return

        try:
            r = rz.resize(self.current_path, largura=largura, altura=altura,
                          manter_proporcao=self.keep_ratio_var.get(),
                          qualidade=qualidade, sobrescrever=sobrescrever)
        except rz.ResizeError as e:
            messagebox.showerror("Não consegui redimensionar", str(e))
            return

        if not r["mudou"]:
            self.resize_label.configure(text=r["aviso"], style="Warning.TLabel")
            return

        texto = "%d × %d  →  %d × %d · %s" % (
            r["de"][0], r["de"][1], r["para"][0], r["para"][1],
            os.path.basename(r["destino"]))
        if r["aviso"]:
            texto += "\n⚠ " + r["aviso"]
        self.resize_label.configure(text=texto, style="Dim.TLabel")

        if sobrescrever:
            self._open_photo(self.current_path)
        elif messagebox.askyesno("Pronto",
                                 "%s\n\nAbrir a cópia redimensionada?" % texto):
            self._open_photo(r["destino"])


    def _fill_agency_fields(self, fields):
        """Preenche o bloco de banco de imagens. As listas suspensas
        guardam o VALOR gravado no arquivo; a tela mostra o rótulo."""
        for widget, valor in ((self.object_name_entry, fields.object_name),
                              (self.alt_text_entry, fields.alt_text)):
            widget.delete(0, "end")
            widget.insert(0, valor or "")
        self.ext_descr_text.delete("1.0", "end")
        self.ext_descr_text.insert("1.0", fields.extended_description or "")

        for var, mapa, valor in (
            (self.digital_source_var, self._digital_map, fields.digital_source),
            (self.model_release_var, self._model_map, fields.model_release),
            (self.property_release_var, self._prop_map, fields.property_release),
        ):
            rotulo = next((r for r, v in mapa.items() if v == (valor or "")), None)
            var.set(rotulo if rotulo else next(iter(mapa)))

    def _update_keywords_counter(self, _event=None):
        """Conta as tags contra o limite do PERFIL ATIVO.

        Um número fixo aqui mentiria: Adobe aceita 49 e Getty 50, e o
        perfil "sem restrições" não tem limite nenhum."""
        n = len(PhotoFields.keywords_from_text(self.keywords_entry.get()))
        perfil = get_profile(self.active_profile_key)
        maximo = perfil.get("max_keywords")
        minimo = perfil.get("min_keywords")

        if maximo and n > maximo:
            self.keywords_counter.configure(
                text="%d tags — acima do limite de %d" % (n, maximo),
                style="Warning.TLabel")
        elif minimo and 0 < n < minimo:
            self.keywords_counter.configure(
                text="%d tag(s) — o perfil recomenda ao menos %d" % (n, minimo),
                style="Warning.TLabel")
        elif maximo:
            self.keywords_counter.configure(
                text="%d de %d tags" % (n, maximo), style="Dim.TLabel")
        else:
            self.keywords_counter.configure(
                text="%d tag(s)" % n, style="Dim.TLabel")

    def _set_date_entry(self, valor):
        self.date_entry.delete(0, "end")
        if valor:
            self.date_entry.insert(0, valor.strftime("%Y-%m-%d %H:%M"))

    def _parse_date_entry(self):
        """Lê a data digitada. Texto inválido devolve None, e o chamador
        mantém a data da câmera — melhor que gravar data errada."""
        texto = self.date_entry.get().strip()
        if not texto:
            return None
        for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                        "%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto, formato)
            except ValueError:
                continue
        return None

    def _render_fileinfo(self, secoes):
        """Desenha a ficha. Reconstrói inteira a cada foto: são poucas
        dezenas de rótulos, e reconstruir é mais simples — e menos sujeito
        a sobra de dado da foto anterior — do que atualizar campo a
        campo."""
        for filho in self.info_frame.winfo_children():
            filho.destroy()

        if not secoes:
            ttk.Label(self.info_frame, text="Abra uma foto para ver a ficha.",
                      style="Dim.TLabel", wraplength=THUMB_MAX,
                      justify="left").pack(anchor="w")
            return

        for titulo, linhas in secoes:
            ttk.Label(self.info_frame, text=titulo.upper(),
                      style="CardMono.TLabel").pack(anchor="w", pady=(8, 2))
            for rotulo, valor in linhas:
                linha = ttk.Frame(self.info_frame)
                linha.pack(fill="x")
                ttk.Label(linha, text=rotulo, style="Dim.TLabel",
                          width=15, anchor="w").pack(side="left")
                ttk.Label(linha, text=valor, wraplength=THUMB_MAX - 130,
                          justify="left").pack(side="left", fill="x", expand=True)

    def _refresh_fileinfo(self):
        try:
            secoes = fi.describe(self.current_path) if self.current_path else []
        except Exception:
            secoes = []
        self._render_fileinfo(secoes)

    def _update_side_labels(self, camera_dt, shorter_edge, gps):
        min_edge = get_profile(self.active_profile_key)["min_edge"]
        if shorter_edge and min_edge and shorter_edge < min_edge:
            self.res_label.configure(
                text="⚠ Menor borda tem %dpx — o perfil ativo exige %dpx."
                     % (shorter_edge, min_edge),
                style="Warning.TLabel")
        elif shorter_edge:
            self.res_label.configure(text="✓ Tamanho compatível com o perfil ativo.",
                                     style="Dim.TLabel")
        else:
            self.res_label.configure(text="Não consegui medir a resolução.",
                                     style="Warning.TLabel")

    def _load_thumbnail(self, path):
        if not PIL_AVAILABLE:
            self.thumb_label.configure(text="(instale 'pillow' para ver preview)")
            return
        try:
            im = Image.open(path)
            im.thumbnail((THUMB_MAX, THUMB_MAX))
            self.thumb_imgtk = ImageTk.PhotoImage(im)
            self.thumb_label.configure(image=self.thumb_imgtk, text="")
        except Exception:
            self.thumb_label.configure(text="(não foi possível gerar preview)")

    def _collect_fields(self) -> PhotoFields:
        caption = self.caption_text.get("1.0", "end-1c").strip()
        headline = self.headline_entry.get().strip()
        instructions = self.instructions_text.get("1.0", "end-1c").strip()
        keywords = PhotoFields.keywords_from_text(self.keywords_entry.get())
        return PhotoFields(
            caption=caption,
            headline=headline,
            instructions=instructions,
            keywords=keywords,
            creator=self.creator_entry.get().strip(),
            creator_url=self.creator_url_entry.get().strip(),
            city=self.city_entry.get().strip(),
            state=self.state_entry.get().strip(),
            country=self.country_entry.get().strip(),
            copyright=self.copyright_entry.get().strip(),
            credit=self.credit_entry.get().strip(),
            source=self.source_entry.get().strip(),
            usage_terms=self.usage_terms_entry.get().strip(),
            sublocation=self.sublocation_entry.get().strip(),
            object_name=self.object_name_entry.get().strip(),
            alt_text=self.alt_text_entry.get().strip(),
            extended_description=self.ext_descr_text.get("1.0", "end-1c").strip(),
            digital_source=self._digital_map.get(self.digital_source_var.get(), ""),
            model_release=self._model_map.get(self.model_release_var.get(), ""),
            property_release=self._prop_map.get(self.property_release_var.get(), ""),
            country_code=self.country_code_entry.get().strip(),
            # a digitada vence a da câmera; em branco mantém a da câmera
            date_created=self._parse_date_entry() or self.current_fields.date_created,
        )

    # -------------------------------------- área de transferência

    def _refresh_clipboard_label(self):
        self.clip_label.configure(text=self.clipboard.summary())

    def on_copy_metadata(self):
        """Copia o que está no formulário — e não o que está gravado no
        arquivo. Assim dá pra ajustar um campo e copiar já corrigido, sem
        precisar salvar antes."""
        if not self.current_path:
            messagebox.showinfo(
                "Nenhuma foto aberta",
                "Abra uma foto primeiro. Para copiar de uma foto sem abri-la, "
                "use \"Copiar de outra foto…\".")
            return
        campos = self._collect_fields()
        origem = os.path.basename(self.current_path) if self.current_path else ""
        self.clipboard.copy_from(campos, self.custom_editor.collect(), origem)
        self._refresh_clipboard_label()
        self.status_label.configure(
            text="Metadados copiados. Abra outra foto e clique em Colar aqui.",
            foreground=theme.SUCCESS)

    def on_paste_metadata(self):
        if not self.current_path:
            messagebox.showinfo(
                "Nenhuma foto aberta",
                "Abra a foto que vai receber os metadados antes de colar.")
            return
        if self.clipboard.is_empty():
            messagebox.showinfo(
                "Nada copiado ainda",
                "Abra uma foto, ajuste os campos e clique em \"Copiar desta foto\".")
            return
        campos = self.clipboard.paste_onto(self._collect_fields())
        self._fill_form_full(campos)
        for tag, valor in self.clipboard.custom.items():
            self.custom_editor.add_row(tag, valor)
        self.status_label.configure(
            text="Metadados colados. Confira antes de salvar — a foto ainda "
                 "não foi alterada.",
            foreground=theme.SUCCESS)

    def on_copy_from_file(self):
        """Lê os metadados de outra foto direto pro clipboard, sem abrir
        essa foto na tela. Serve pra usar uma foto de referência já
        etiquetada como molde."""
        caminho = filedialog.askopenfilename(
            title="Copiar metadados de qual foto?",
            filetypes=[("Imagens", "*.jpg *.jpeg *.tif *.tiff *.png"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            campos = read_existing_fields(caminho)
        except ExifToolNotFound as e:
            messagebox.showerror("ExifTool não encontrado", str(e))
            return
        except Exception as e:
            messagebox.showerror("Não consegui ler", str(e))
            return
        self.clipboard.copy_from(campos, {}, os.path.basename(caminho))
        self._refresh_clipboard_label()
        self.status_label.configure(
            text="Copiado de %s. Clique em Colar aqui." % os.path.basename(caminho),
            foreground=theme.SUCCESS)

    def on_clear_clipboard(self):
        self.clipboard.clear()
        self._refresh_clipboard_label()

    def _fill_form_full(self, fields: PhotoFields):
        """Preenche TODOS os campos, inclusive os \"de casa\".

        Diferente de _fill_form, que só sobrescreve autor/local/direitos
        quando o arquivo já os tinha — ali a regra existe pra não apagar o
        que veio das preferências. Ao colar, a intenção é explícita: o
        usuário quer aqueles valores.

        Destrava os campos antes de escrever. O Tk ignora `insert` em
        widget desabilitado EM SILÊNCIO — sem erro, sem aviso — e os
        campos de foto nascem travados até uma foto ser aberta. Sem isto,
        colar parecia funcionar e metade dos campos ficava vazia."""
        travados = self.caption_text.cget("state") == "disabled"
        if travados:
            self._set_photo_fields_enabled(True)
        self.caption_text.delete("1.0", "end")
        self.caption_text.insert("1.0", fields.caption)
        self._update_caption_counter()
        self.headline_entry.delete(0, "end")
        self.headline_entry.insert(0, fields.headline)
        self.instructions_text.delete("1.0", "end")
        self.instructions_text.insert("1.0", fields.instructions)
        self.keywords_entry.delete(0, "end")
        self.keywords_entry.insert(0, fields.keywords_as_text())
        widgets = self._sticky_widgets()
        for key in STICKY_FIELD_KEYS:
            widgets[key].delete(0, "end")
            widgets[key].insert(0, getattr(fields, key, "") or "")
        self._fill_agency_fields(fields)
        self._update_keywords_counter()
        if travados:
            self._set_photo_fields_enabled(False)

    # ------------------------------------------------------------ gravação

    def on_save(self):
        if not self.current_path:
            return

        fields = self._collect_fields()
        issues = validate(fields, self.current_shorter_edge, self.active_profile_key)

        if issues:
            proceed = show_issues_dialog(self, "Itens pendentes", issues)
            if not proceed:
                return

        custom_fields = self.custom_editor.collect()
        try:
            write_metadata(self.current_path, fields, keep_backup=self.keep_backup_var.get(), custom_fields=custom_fields)
        except (ExifToolNotFound, MetadataWriteError) as e:
            messagebox.showerror("Erro ao salvar", str(e))
            return

        save_prefs(self._current_sticky_prefs())
        self.status_label.configure(text="Metadados salvos com sucesso.", foreground=theme.SUCCESS)
        messagebox.showinfo("Salvo", "Metadados gravados no arquivo com sucesso.")

    def on_open_batch(self):
        BatchWindow(self)


BATCH_FIELD_ORDER = [
    "caption", "headline", "instructions", "keywords",
    "creator", "creator_url", "city", "state", "country",
    "copyright", "credit", "source", "usage_terms",
]


class BatchWindow(tk.Toplevel):
    """Aplica valores em massa a várias fotos de uma vez — campo por campo:
    só os campos marcados como 'aplicar a todas' são gravados; os demais
    campos de cada foto (ex.: legenda individual) ficam intocados."""

    def __init__(self, master: MetadataTab):
        super().__init__(master)
        self.configure(bg=theme.BG)
        self.master_app = master
        self.title("Processar em lote")
        self.geometry("760x760")
        self.minsize(680, 640)
        self.transient(master.winfo_toplevel())

        self.paths: list = []

        self._build_ui()

        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.files_list.drop_target_register(DND_FILES)
            self.files_list.dnd_bind("<<Drop>>", self._on_drop)

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Button(top, text="Escolher pasta...", command=self.on_choose_folder).pack(side="left")
        ttk.Button(top, text="Adicionar fotos...", command=self.on_add_files).pack(side="left", padx=6)
        ttk.Button(top, text="Remover selecionadas", command=self.on_remove_selected).pack(side="left")
        self.count_label = ttk.Label(top, text="0 fotos selecionadas", foreground=theme.FG_DIM)
        self.count_label.pack(side="right")

        list_frame = ttk.Frame(self, padding=(10, 0))
        list_frame.pack(fill="both", expand=False)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical")
        self.files_list = tk.Listbox(list_frame, height=6, selectmode="extended", yscrollcommand=list_scroll.set)
        list_scroll.configure(command=self.files_list.yview)
        self.files_list.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")

        if not DND_AVAILABLE:
            ttk.Label(self, text="(arrastar-e-soltar indisponível — use os botões acima)", foreground=theme.FG_DIM).pack(anchor="w", padx=10)

        ttk.Separator(self).pack(fill="x", pady=10)

        hint = ttk.Label(
            self,
            text="Marque \"aplicar\" só nos campos que devem ser gravados IGUAIS em todas as "
            "fotos selecionadas (ex.: local, palavras-chave, criador). Campos não marcados não são "
            "tocados — cada foto mantém o que já tinha (ex.: legenda individual).",
            wraplength=720, justify="left", foreground=theme.FG_DIM,
        )
        hint.pack(fill="x", padx=10, pady=(0, 10))

        # Botões e status ficam empacotados no rodapé ANTES da área de
        # campos (que é expansível) — senão a área expansível toma todo o
        # espaço da janela e o rodapé fica espremido a quase-zero de altura.
        bottom_container = ttk.Frame(self)
        bottom_container.pack(side="bottom", fill="x")

        bottom = ttk.Frame(bottom_container, padding=10)
        bottom.pack(fill="x")
        self.keep_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text="Manter cópia de segurança (_original)", variable=self.keep_backup_var).pack(side="left")
        self.save_csv_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text="Salvar log CSV do processamento", variable=self.save_csv_var).pack(side="left", padx=(15, 0))
        ttk.Button(bottom, text="Processar lote", command=self.on_process).pack(side="right")
        ttk.Button(bottom, text="Fechar", command=self.destroy).pack(side="right", padx=(0, 8))

        self.status_label = ttk.Label(bottom_container, text="", foreground=theme.SUCCESS, padding=(10, 0))
        self.status_label.pack(anchor="w")

        fields_container = ttk.Frame(self, padding=(10, 0))
        fields_container.pack(fill="both", expand=True)
        canvas = tk.Canvas(fields_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(fields_container, orient="vertical", command=canvas.yview)
        form = ttk.Frame(canvas)
        form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form, anchor="nw", width=680)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._fields_canvas = canvas
        self._fields_form = form

        self.apply_vars = {}
        self.value_widgets = {}
        prefs = load_prefs()
        for key in BATCH_FIELD_ORDER:
            row = ttk.Frame(form)
            row.pack(fill="x", pady=3)
            var = tk.BooleanVar(value=key in BATCH_DEFAULT_CHECKED)
            self.apply_vars[key] = var
            ttk.Checkbutton(row, variable=var, text="aplicar").pack(side="left")
            ttk.Label(row, text=FIELD_LABELS[key] + ":", width=24).pack(side="left")
            entry = ttk.Entry(row)
            entry.pack(side="left", fill="x", expand=True)
            if key in STICKY_FIELD_KEYS and prefs.get(key):
                entry.insert(0, prefs[key])
            self.value_widgets[key] = entry

        ttk.Separator(form).pack(fill="x", pady=10)
        # ------------------------------------------- banco de imagens
        ttk.Separator(right).pack(fill="x", pady=(14, 0))
        ttk.Label(right, text="Banco de imagens", style="Section.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(
            right,
            text="Campos que as agências passaram a exigir. Sem a declaração de "
                 "origem, envios com IA são recusados; sem status de liberação, "
                 "foto com pessoa reconhecível também.",
            style="Dim.TLabel", wraplength=640, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        ttk.Label(right, text="Título de venda (curto — é o que aparece na busca):").pack(anchor="w")
        self.object_name_entry = ttk.Entry(right)
        self.object_name_entry.pack(fill="x")

        ttk.Label(right, text="Texto alternativo (acessibilidade — descreva a imagem em uma frase):").pack(anchor="w", pady=(8, 0))
        self.alt_text_entry = ttk.Entry(right)
        self.alt_text_entry.pack(fill="x")

        ttk.Label(right, text="Descrição estendida (acessibilidade — opcional):").pack(anchor="w", pady=(8, 0))
        self.ext_descr_text = tk.Text(right, height=2, wrap="word")
        theme.style_text_card(self.ext_descr_text)
        self.ext_descr_text.pack(fill="x")

        origem_frame = ttk.Frame(right)
        origem_frame.pack(fill="x", pady=(8, 0))
        col_a = ttk.Frame(origem_frame)
        col_a.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(col_a, text="Origem digital (declaração de IA):").pack(anchor="w")
        self._digital_labels = [rot for _iri, rot in DIGITAL_SOURCES]
        self._digital_map = {rot: iri for iri, rot in DIGITAL_SOURCES}
        self.digital_source_var = tk.StringVar(value=self._digital_labels[0])
        ttk.Combobox(col_a, textvariable=self.digital_source_var, state="readonly",
                     values=self._digital_labels).pack(fill="x")

        rel_frame = ttk.Frame(right)
        rel_frame.pack(fill="x", pady=(8, 0))
        col_b = ttk.Frame(rel_frame)
        col_b.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(col_b, text="Liberação de modelo:").pack(anchor="w")
        self._model_labels = [rot for _v, rot in RELEASE_STATUSES]
        self._model_map = {rot: v for v, rot in RELEASE_STATUSES}
        self.model_release_var = tk.StringVar(value=self._model_labels[0])
        ttk.Combobox(col_b, textvariable=self.model_release_var, state="readonly",
                     values=self._model_labels).pack(fill="x")
        col_c = ttk.Frame(rel_frame)
        col_c.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Label(col_c, text="Liberação de propriedade:").pack(anchor="w")
        self._prop_labels = [rot for _v, rot in PROPERTY_RELEASE_STATUSES]
        self._prop_map = {rot: v for v, rot in PROPERTY_RELEASE_STATUSES}
        self.property_release_var = tk.StringVar(value=self._prop_labels[0])
        ttk.Combobox(col_c, textvariable=self.property_release_var, state="readonly",
                     values=self._prop_labels).pack(fill="x")

        ttk.Separator(right).pack(fill="x", pady=(14, 0))
        self._build_resize_section(right)

        self.custom_editor = CustomFieldsEditor(
            form,
            "Grava qualquer tag do ExifTool em TODAS as fotos selecionadas (ex.: \"XMP:Rating\"). "
            "Diferente dos campos acima, aqui não tem caixa de \"aplicar\" — todo campo adicionado é aplicado.",
        )
        self.custom_editor.pack(fill="x", pady=(0, 10))

        bind_mousewheel(self._fields_canvas, self._fields_form)

    # ---------------------------------------------------------- seleção
    def _add_paths(self, new_paths):
        added = 0
        for p in new_paths:
            if p not in self.paths and os.path.isfile(p):
                self.paths.append(p)
                self.files_list.insert("end", os.path.basename(p))
                added += 1
        self.count_label.configure(text=f"{len(self.paths)} fotos selecionadas")
        return added

    def on_choose_folder(self):
        folder = filedialog.askdirectory(title="Escolha a pasta com as fotos")
        if not folder:
            return
        files = list_image_files(folder)
        if not files:
            messagebox.showinfo("Pasta sem fotos", "Não encontrei fotos suportadas (.jpg/.jpeg/.tif/.tiff/.png) nessa pasta.")
            return
        self._add_paths(files)

    def on_add_files(self):
        files = filedialog.askopenfilenames(
            title="Escolha as fotos",
            filetypes=[("Imagens", "*.jpg *.jpeg *.tif *.tiff *.png"), ("Todos os arquivos", "*.*")],
        )
        if files:
            self._add_paths(list(files))

    def on_remove_selected(self):
        selected = list(self.files_list.curselection())
        for idx in reversed(selected):
            del self.paths[idx]
            self.files_list.delete(idx)
        self.count_label.configure(text=f"{len(self.paths)} fotos selecionadas")

    def _on_drop(self, event):
        dropped = extract_dropped_paths(event)
        expanded = []
        for p in dropped:
            if os.path.isdir(p):
                expanded.extend(list_image_files(p))
            elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in {".jpg", ".jpeg", ".tif", ".tiff", ".png"}:
                expanded.append(p)
        if expanded:
            self._add_paths(expanded)

    # ---------------------------------------------------------- processamento
    def _build_batch_fields(self) -> PhotoFields:
        keywords = PhotoFields.keywords_from_text(self.value_widgets["keywords"].get())
        return PhotoFields(
            caption=self.value_widgets["caption"].get().strip(),
            headline=self.value_widgets["headline"].get().strip(),
            instructions=self.value_widgets["instructions"].get().strip(),
            keywords=keywords,
            creator=self.value_widgets["creator"].get().strip(),
            creator_url=self.value_widgets["creator_url"].get().strip(),
            city=self.value_widgets["city"].get().strip(),
            state=self.value_widgets["state"].get().strip(),
            country=self.value_widgets["country"].get().strip(),
            copyright=self.value_widgets["copyright"].get().strip(),
            credit=self.value_widgets["credit"].get().strip(),
            source=self.value_widgets["source"].get().strip(),
            usage_terms=self.value_widgets["usage_terms"].get().strip(),
        )

    def _preflight_issues(self, fields: PhotoFields, apply_fields: set) -> list:
        profile = get_profile(self.master_app.active_profile_key)
        required = profile["required"]
        issues = []

        if "caption" in apply_fields:
            if profile["caption_max_len"] and len(fields.caption) > profile["caption_max_len"]:
                issues.append(f"Legenda em lote tem {len(fields.caption)} caracteres (máximo {profile['caption_max_len']}).")
            found = [ch for ch in profile["forbidden_chars"] if ch in fields.caption]
            if found:
                issues.append("Legenda em lote contém caractere(s) não permitido(s): " + " ".join(found))
            if "caption" in required and not fields.caption:
                issues.append("Legenda em lote está marcada pra aplicar, mas está vazia.")

        if "keywords" in apply_fields and "keywords" in required and not fields.keywords:
            issues.append("Palavras-chave em lote estão marcadas pra aplicar, mas nenhuma foi preenchida.")

        for key in ("creator", "city", "state", "country"):
            if key in apply_fields and key in required and not getattr(fields, key):
                issues.append(f"{FIELD_LABELS[key]} em lote está marcado pra aplicar, mas está vazio.")

        if profile["min_edge"]:
            small = []
            for p in self.paths:
                try:
                    edge = get_shorter_edge(p)
                except (ExifToolNotFound, MetadataWriteError):
                    edge = None
                if edge is None or edge < profile["min_edge"]:
                    small.append(os.path.basename(p))
            if small:
                issues.append(
                    f"{len(small)} foto(s) abaixo da resolução mínima do perfil ({profile['min_edge']}px): "
                    + ", ".join(small[:8]) + (", ..." if len(small) > 8 else "")
                )

        return issues

    def on_process(self):
        if not self.paths:
            messagebox.showinfo("Nenhuma foto selecionada", "Escolha uma pasta ou adicione fotos primeiro.")
            return

        apply_fields = {key for key, var in self.apply_vars.items() if var.get()}
        custom_fields = self.custom_editor.collect()
        if not apply_fields and not custom_fields:
            messagebox.showinfo("Nenhum campo marcado", "Marque pelo menos um campo (ou adicione um campo personalizado) pra aplicar em lote.")
            return

        fields = self._build_batch_fields()

        issues = self._preflight_issues(fields, apply_fields)
        if issues:
            proceed = show_issues_dialog(self, "Itens pendentes no lote", issues)
            if not proceed:
                return

        applied_labels = ", ".join(FIELD_LABELS[k] for k in BATCH_FIELD_ORDER if k in apply_fields)
        if custom_fields:
            applied_labels += (", " if applied_labels else "") + ", ".join(custom_fields.keys())
        if not messagebox.askyesno(
            "Confirmar processamento em lote",
            f"Isso vai alterar {len(self.paths)} arquivo(s), gravando: {applied_labels}.\n\n"
            "Os demais campos de cada foto não serão tocados. Continuar?",
        ):
            return

        self.status_label.configure(text=f"Processando {len(self.paths)} fotos...", foreground=theme.FG_DIM)
        self.update_idletasks()

        # nomes de tag inválidos em campos personalizados viram erro por
        # arquivo (não interrompem o lote) — aparecem no resumo abaixo
        results = write_metadata_batch(
            self.paths, fields, apply_fields, keep_backup=self.keep_backup_var.get(), custom_fields=custom_fields
        )
        ok_count = sum(1 for r in results if r.ok)
        err_count = len(results) - ok_count

        csv_note = ""
        if self.save_csv_var.get():
            base_folder = os.path.dirname(self.paths[0])
            csv_name = f"log-lote-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
            csv_path = os.path.join(base_folder, csv_name)
            try:
                write_batch_log_csv(csv_path, results, sorted(apply_fields, key=BATCH_FIELD_ORDER.index))
                csv_note = f"\n\nLog salvo em:\n{csv_path}"
            except OSError as e:
                csv_note = f"\n\n(Não consegui salvar o log CSV: {e})"

        # persiste os campos "de casa" usados no lote como preferências
        sticky_updates = {k: getattr(fields, k) for k in STICKY_FIELD_KEYS if k in apply_fields and getattr(fields, k)}
        if sticky_updates:
            current_prefs = load_prefs()
            current_prefs.update(sticky_updates)
            save_prefs(current_prefs)

        self.status_label.configure(text=f"Lote concluído: {ok_count} ok, {err_count} erro(s).", foreground=theme.SUCCESS if err_count == 0 else theme.ERROR)

        summary = f"{ok_count} de {len(results)} fotos atualizadas com sucesso."
        if err_count:
            failed_names = [os.path.basename(r.path) + ": " + r.error for r in results if not r.ok]
            summary += "\n\nErros:\n" + "\n".join(failed_names[:10])
            if len(failed_names) > 10:
                summary += f"\n... e mais {len(failed_names) - 10}."
        summary += csv_note
        messagebox.showinfo("Processamento em lote concluído", summary)
