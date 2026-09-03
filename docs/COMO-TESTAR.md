# Como baixar, instalar e testar

Guia para quem vai testar o Metadados 81. Não precisa saber programar.

---

## macOS

### 1. Baixar

Vá em **[Releases](../../releases/latest)** e baixe o arquivo
`Metadados81-1.0.0.dmg` (27 MB).

### 2. Instalar

Abra o `.dmg` e arraste **Metadados 81** para a pasta Aplicativos.

### 3. Abrir na primeira vez — atenção, este passo é o que trava todo mundo

O app **não é notarizado pela Apple**, então o macOS vai bloquear.
Clicar duas vezes **não funciona**: aparece só uma janela dizendo que o
app está danificado ou não pode ser aberto, e o único botão é "Mover
para o Lixo". O app não está danificado — é só a Apple exigindo
pagamento anual de quem distribui software.

Faça assim:

1. Abra a pasta **Aplicativos**
2. **Clique com o botão direito** em "Metadados 81" (ou Control+clique)
3. Escolha **Abrir**
4. Na janela que aparecer, clique em **Abrir** de novo

Pronto. A partir daí ele abre normalmente com dois cliques.

Se mesmo assim não abrir, vá em **Ajustes do Sistema → Privacidade e
Segurança**, role até o fim, e clique em **Abrir assim mesmo** no aviso
sobre o Metadados 81.

---

## Windows

Ainda não existe um `.exe` pronto para baixar — ele precisa ser
construído numa máquina Windows. São uns 5 minutos.

### 1. Instalar o Python

Baixe em **[python.org/downloads](https://www.python.org/downloads/)**.

> **Importante:** tem que ser o do python.org, **não** o da Microsoft
> Store. O da Store roda numa caixa isolada e não enxerga direito a
> biblioteca gráfica que o app usa — o programa abriria com as janelas
> em branco.

Na tela do instalador, marque **"Add python.exe to PATH"** antes de
clicar em Install.

### 2. Baixar o código

Nesta página, botão verde **Code** → **Download ZIP**. Descompacte em
algum lugar fácil, por exemplo a Área de Trabalho.

### 3. Construir

Abra a pasta descompactada, clique na barra de endereço do Explorer,
digite `powershell` e dê Enter. Na janela azul que abrir, cole:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

O script confere se está tudo certo, baixa o ExifTool, monta o programa
e testa sozinho se ele abre. No fim ele diz onde ficou o arquivo:
`dist\Metadados81-1.0.0-windows.zip`.

### 4. Rodar

Descompacte esse zip e clique em **Metadados81.exe**.

Na primeira vez o Windows vai avisar que o app é de origem desconhecida
— clique em **Mais informações** e depois em **Executar assim mesmo**.
É o mesmo motivo do macOS: o app não tem certificado de assinatura.

---

## O que testar

Não precisa seguir à risca, mas estes são os caminhos que mais importam:

1. **Abrir uma foto** — arraste um JPEG para a janela. Confira se a
   ficha técnica embaixo da miniatura bate com a foto (câmera, ISO,
   dimensões).
2. **Preencher e salvar** — escreva legenda, palavras-chave e cidade,
   e clique em Salvar metadados. Depois feche e abra a mesma foto: o
   que você escreveu tem que reaparecer.
3. **Escolher um perfil de agência** no alto e salvar de novo — ele
   deve listar o que está faltando para aquela agência.
4. **Copiar e colar** — copie os metadados de uma foto e cole em outra.
5. **Redimensionar** — use uma foto **na vertical** e confira se a
   cópia continua em pé e mantém os metadados.
6. **Processar em lote** — selecione uma pasta e aplique só alguns
   campos marcados.

## Se algo der errado

Anote o que você estava fazendo e o que apareceu na tela — print ajuda
muito. Erros mais úteis de relatar:

- o app não abre, ou abre com a janela em branco
- alguma coisa que você escreveu não foi salva
- a foto redimensionada saiu deitada, sem metadados ou com aparência ruim
- algum botão que não faz nada

## Seus arquivos estão seguros?

- O app **não envia nada para lugar nenhum** — sem nuvem, sem conta,
  sem internet.
- Por padrão, toda vez que grava metadados ele deixa uma cópia do
  arquivo original ao lado, com `_original` no nome.
- O redimensionamento cria um arquivo novo e **não toca no original**,
  a menos que você marque para sobrescrever.

Ainda assim, para testar, prefira cópias das fotos — não o único
arquivo de um trabalho.
