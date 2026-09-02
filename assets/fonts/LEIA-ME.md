# Fontes embutidas

O CineBrain OS embute duas fontes porque **nenhuma delas existe de fábrica
no macOS ou no Windows**, e a identidade visual do app depende delas. São
registradas em tempo de execução (ver `platform_utils.register_bundled_fonts`),
sem instalar nada no sistema do usuário.

| Arquivo | Família | Uso |
|---|---|---|
| `DMSans.ttf` | DM Sans | toda a interface |
| `JetBrainsMono.ttf` | JetBrains Mono | dado técnico: caminho, checksum, tag ExifTool |

Ambas são variáveis (um arquivo cobre todos os pesos).

## Licença

Ambas sob **SIL Open Font License 1.1** (`OFL.txt`), que permite
redistribuição embutida em aplicativos, inclusive comerciais. A licença
exige que o texto dela acompanhe as fontes — é por isso que `OFL.txt`
está aqui e deve continuar sendo distribuído junto.

Origem: https://github.com/google/fonts
