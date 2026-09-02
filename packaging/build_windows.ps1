# Constrói o Metadados 81 para Windows.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# Produz dist\Metadados81-2.0.0-windows.zip — uma pasta que roda direto,
# sem instalador. Quem receber descompacta e clica em Metadados81.exe.
#
# PRÉ-REQUISITO: Python do python.org (NÃO o da Microsoft Store).
# O da Store roda em sandbox e não enxerga o Tcl/Tk direito. O instalador
# oficial já traz Tk 8.6, que é o que o app exige.

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$Versao = "1.0.0"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Write-Host "==> Projeto: $Raiz"
Write-Host ""

Write-Host "==> Conferindo Python e Tcl/Tk"
& $Python -c @"
import sys, tkinter
r = tkinter.Tk(); nivel = r.tk.call('info','patchlevel'); r.destroy()
partes = tuple(int(p) for p in str(nivel).split('.')[:2])
print('    Python %s, Tcl/Tk %s' % (sys.version.split()[0], nivel))
if partes < (8, 6):
    print('    ERRO: o app precisa de Tcl/Tk 8.6+.')
    print('    Instale o Python do python.org, nao o da Microsoft Store.')
    sys.exit(1)
"@
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host ""

Write-Host "==> Instalando dependencias"
& $Python -m pip install --quiet --upgrade pip
& $Python -m pip install --quiet -r "$Raiz\requirements.txt" pyinstaller
Write-Host ""

Write-Host "==> Gerando icone"
& $Python "$Raiz\packaging\make_icon.py"
Write-Host ""

Write-Host "==> Preparando o ExifTool"
# No Windows nao existe Perl de sistema: baixa o .exe autocontido oficial
& $Python "$Raiz\packaging\fetch_exiftool.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "    AVISO: sem ExifTool embutido. O app abre, mas a aba de"
    Write-Host "    Metadados so funciona se houver ExifTool instalado na maquina."
}
Write-Host ""

Write-Host "==> PyInstaller"
Push-Location $Raiz
& $Python -m PyInstaller "$Raiz\packaging\metadados81.spec" --noconfirm --clean
Pop-Location
Write-Host ""

$Pasta = "$Raiz\dist\Metadados81"
$Exe = "$Pasta\Metadados81.exe"
if (-not (Test-Path $Exe)) { Write-Host "ERRO: $Exe nao foi criado"; exit 1 }

Write-Host "==> Teste de fumaca: o app abre?"
& $Exe --smoke-test
if ($LASTEXITCODE -ne 0) {
    Write-Host "    AVISO: o teste de fumaca falhou. Abra o exe a mao para ver o erro."
} else {
    Write-Host "    abriu e fechou OK"
}
Write-Host ""

Write-Host "==> Compactando"
$Zip = "$Raiz\dist\Metadados81-$Versao-windows.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path $Pasta -DestinationPath $Zip
Write-Host ""
Write-Host "PRONTO"
Write-Host "  ZIP: $Zip"
Write-Host ""
Write-Host "Quem receber: descompacta e clica em Metadados81.exe."
Write-Host "O Windows SmartScreen vai avisar que o app e de origem desconhecida"
Write-Host "na primeira vez — clicar em 'Mais informacoes' e 'Executar assim mesmo'."
Write-Host "O app nao tem certificado de assinatura de codigo."
