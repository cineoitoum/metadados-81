#!/usr/bin/env bash
# Constrói o Metadados 81.app e o DMG.
#
#   bash packaging/build_macos.sh
#
# POR QUE CONSTRUIR FORA DA PASTA DO PROJETO:
# se o projeto estiver num volume de nuvem (pCloud, Drive, Dropbox), o
# executável dentro do .app nasce SEM bit de execução — esses volumes
# descartam a permissão em silêncio — e o app não abre. Por isso o build
# acontece em disco local e só o DMG pronto volta para o projeto.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NOME="Metadados 81"
VERSAO="1.0.0"

PYTHON="${PYTHON:-python3}"
TRABALHO="$(mktemp -d -t metadados81-build)"
trap 'rm -rf "$TRABALHO"' EXIT

echo "==> Projeto:  $RAIZ"
echo "==> Trabalho: $TRABALHO"
echo

echo "==> Conferindo o Tcl/Tk do Python"
"$PYTHON" - <<'PY'
import sys, tkinter
r = tkinter.Tk(); nivel = r.tk.call("info", "patchlevel"); r.destroy()
partes = tuple(int(p) for p in str(nivel).split(".")[:2])
print("    Python %s, Tcl/Tk %s" % (sys.version.split()[0], nivel))
if partes < (8, 6):
    print("    ERRO: o app precisa de Tcl/Tk 8.6+. Com a 8.5 as janelas")
    print("    abrem em branco. Use um Python do Homebrew: brew install python-tk")
    sys.exit(1)
PY
echo

echo "==> Gerando ícones"
"$PYTHON" "$RAIZ/packaging/make_icon.py"
echo

echo "==> Preparando o ExifTool"
"$PYTHON" "$RAIZ/packaging/fetch_exiftool.py" || \
  echo "    (seguindo sem ExifTool embutido — o app usará o do sistema)"
echo

echo "==> PyInstaller"
cd "$RAIZ"
"$PYTHON" -m PyInstaller "$RAIZ/packaging/metadados81.spec" \
  --noconfirm --clean \
  --distpath "$TRABALHO/dist" \
  --workpath "$TRABALHO/build"
echo

APP="$TRABALHO/dist/$APP_NOME.app"
[ -d "$APP" ] || { echo "ERRO: $APP não foi criado"; exit 1; }

# o bit de execução tem de estar aqui, senão o app não abre
chmod +x "$APP/Contents/MacOS/$APP_NOME" 2>/dev/null || true
echo "==> App construído: $(du -sh "$APP" | cut -f1)"

echo "==> Assinatura ad-hoc"
# sem isso o macOS mata o app em Apple Silicon ("está danificado").
# Não é notarização — quem receber ainda precisa liberar em Ajustes >
# Privacidade e Segurança na primeira abertura.
codesign --force --deep --sign - "$APP" 2>/dev/null \
  && echo "    assinado (ad-hoc)" \
  || echo "    AVISO: não consegui assinar; o app pode ser bloqueado"
echo

echo "==> Teste de fumaça: o app abre?"
"$APP/Contents/MacOS/$APP_NOME" --smoke-test && echo "    abriu e fechou OK" \
  || echo "    AVISO: o teste de fumaça falhou — abra o app à mão para ver o erro"
echo

echo "==> Teste de abertura pelo Finder"
# O smoke-test roda o binario DIRETO. O usuario abre pelo Finder, que
# manda AppleEvents — e foi exatamente ai que o argv_emulation derrubava
# o app enquanto todos os testes passavam. Um teste que nao reproduz o
# gesto do usuario nao cobre o defeito do usuario.
open -a "$APP"
sleep 6
if pgrep -f "$APP_NOME" >/dev/null 2>&1; then
  echo "    abriu pelo Finder e continua rodando"
  pkill -f "$APP_NOME" 2>/dev/null || true
else
  echo "    ERRO: o app NAO sobreviveu ao ser aberto pelo Finder."
  CRASH=$(ls -t "$HOME/Library/Logs/DiagnosticReports/$APP_NOME"*.ips 2>/dev/null | head -1)
  [ -n "$CRASH" ] && echo "    relatorio de crash: $CRASH"
  echo "    O DMG nao sera gerado."
  exit 1
fi
echo

echo "==> Montando o DMG"
DMG_STAGE="$TRABALHO/dmg"
mkdir -p "$DMG_STAGE"
cp -R "$APP" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
DMG="$TRABALHO/Metadados81-$VERSAO.dmg"
hdiutil create -volname "$APP_NOME" -srcfolder "$DMG_STAGE" \
  -ov -format UDZO "$DMG" >/dev/null

SAIDA="$RAIZ/dist"
mkdir -p "$SAIDA"
cp "$DMG" "$SAIDA/"
echo
echo "PRONTO"
echo "  DMG: $SAIDA/$(basename "$DMG")  ($(du -sh "$DMG" | cut -f1))"
echo
echo "Quem receber precisa, na primeira abertura: clicar com o botão"
echo "direito no app e escolher Abrir — ou liberar em Ajustes do Sistema >"
echo "Privacidade e Segurança. O app não é notarizado pela Apple."
