# Metadados 81

**Edição de metadados IPTC/XMP de fotos.** Um programa, uma janela — e a
capacidade de copiar os metadados de uma foto e colar na próxima.

![Versão](https://img.shields.io/badge/vers%C3%A3o-1.0-FE8254)
![macOS](https://img.shields.io/badge/macOS-11+-3F5A62)
![Windows](https://img.shields.io/badge/Windows-10+-3F5A62)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-3F5A62)

> Recorte do **CineBrain OS**: é a aba de Metadados dele, transformada em
> produto próprio para quem só precisa etiquetar fotos.

---

## O que faz

- Preenche legenda, título, descrição, palavras-chave, autor, local,
  direitos, crédito, fonte e termos de uso — em **IPTC e XMP ao mesmo
  tempo**, que é o que os bancos de imagem e as redações leem.
- Grava **qualquer tag do ExifTool** além do conjunto padrão, digitando o
  nome dela.
- **Copia e cola metadados entre fotos.**
- Processa **em lote**, escolhendo por campo o que se repete em todas.
- Valida antes de gravar: tamanho mínimo, comprimento de legenda,
  caracteres proibidos e campos obrigatórios.
- Mostra data e GPS que vieram da câmera.

A imagem **não é recomprimida**. O ExifTool reescreve apenas os blocos de
metadado; os pixels ficam byte a byte idênticos.

## Copiar e colar metadados

O gesto para o qual isto existe: você etiquetou uma foto e a próxima é do
mesmo trabalho — mesmo autor, mesma cidade, mesmos direitos, quase a
mesma legenda.

| Botão | O que faz |
|---|---|
| **Copiar desta foto** | Guarda o que está no formulário — inclusive alterações ainda não salvas |
| **Colar aqui** | Aplica na foto aberta. Nada é gravado até você clicar em Salvar |
| **Copiar de outra foto…** | Lê os metadados de um arquivo sem abri-lo, para usar como molde |

Duas decisões que valem saber:

**Data de captura e GPS não são copiados.** Vêm da câmera e são de cada
foto; copiá-los produziria metadado errado — pior que metadado ausente.

**Campo vazio na cópia não apaga o destino.** Colar acrescenta o que foi
copiado, não zera o que já havia. Para limpar um campo, apague na tela.

A área de transferência **sobrevive a fechar o programa** — é comum
copiar de uma foto hoje e colar noutra amanhã.

## Instalação

Baixe o instalador em [Releases](../../releases).

- **macOS** — abra o `.dmg`, arraste para Aplicativos e, na primeira vez,
  clique com o **botão direito › Abrir** (não é notarizado pela Apple).
- **Windows** — descompacte e execute `Metadados81.exe`. O SmartScreen
  avisa na primeira vez: **Mais informações › Executar assim mesmo**.

Não é preciso instalar Python, ExifTool nem fontes.

## Rodando do código-fonte

```bash
pip install -r requirements.txt
python src/app.py
```

⚠️ **Precisa de Tcl/Tk 8.6+.** Com a 8.5 as janelas abrem em branco — é
limitação do Tk antigo que a Apple mantém no macOS, não defeito do app, e
ele detecta e explica na inicialização.

```bash
python3 -c "import tkinter; r=tkinter.Tk(); print(r.tk.call('info','patchlevel'))"
```

Se aparecer `8.5.x`: `brew install python-tk` no macOS; no Windows, use o
Python do python.org (não o da Microsoft Store).

## Construindo o instalador

```bash
bash packaging/build_macos.sh
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

## Onde ficam seus dados

| Sistema | Pasta |
|---|---|
| macOS | `~/Library/Application Support/Metadados 81/` |
| Windows | `%APPDATA%\Metadados 81\` |

Guarda só suas preferências de autor/local/direitos e a área de
transferência. Nenhuma foto é copiada para lá.

## Créditos

[ExifTool](https://exiftool.org), de Phil Harvey.
[DM Sans](https://fonts.google.com/specimen/DM+Sans) e
[JetBrains Mono](https://www.jetbrains.com/lp/mono/), sob
[SIL OFL 1.1](assets/fonts/OFL.txt).

Licença [MIT](LICENSE).
