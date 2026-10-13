# Formato `.MIX` (MotoGP 08, PS2, SLUS-21811)

Pacote de arquivos da Milestone. Validado nos 33 `.MIX` da ISO americana
(4.461 arquivos): o índice de todos termina exatamente no fim do arquivo.
Ferramenta: `tools/mix.py`.

Todos os inteiros são little-endian.

## Cabeçalho (0x20 bytes)

| Offset | Tipo  | Conteúdo |
| ------ | ----- | -------- |
| 0x00   | u32   | sempre 0 |
| 0x04   | u32   | número de arquivos |
| 0x08   | u32   | offset absoluto do índice (fica depois dos dados) |
| 0x0C   | 20 B  | zeros |

Os dados dos arquivos começam em 0x20.

## Índice

Uma entrada por arquivo, em sequência, sem alinhamento:

| Tipo        | Conteúdo |
| ----------- | -------- |
| u32         | tamanho do nome em bytes (inclui o `\0` final) |
| bytes       | nome cifrado |
| u32         | offset absoluto dos dados |
| u32         | tamanho armazenado |
| u32         | tamanho descompactado (igual ao armazenado quando não há compressão) |
| u8          | flag: 0 = normal, 1 = compactado |
| 8 bytes     | desconhecido. Os 4 primeiros parecem a metade alta de um FILETIME do Windows (2007–2008). Preservar ao reempacotar. |

### Nome

`nome[i] = cifrado[i] XOR ((0x3A * i) & 0xFF)`, em ASCII maiúsculo, com `\`
como separador e terminado em `\0`. Exemplo: `TRACKS\JEREZ\JEREZ.SPL`.

### Compressão

Só 80 dos 4.461 arquivos estão compactados (flag 1): os 76 de `TRACKS.MIX`
e 4 de `DATA.MIX`. O algoritmo ainda não foi identificado. Motos, pilotos e
pistas estão todos sem compressão.

## O que há dentro (resumo)

| Extensão | O que é |
| -------- | ------- |
| `.SLF` / `.SLI` | Cenas/modelos 3D no formato próprio da engine ("Selene Scene File", versão 2.05) |
| `.TXD` | Dicionário de texturas RenderWare (chunk 0x16) |
| `.TXS` | Texto com a configuração de texturas/materiais da cena |
| `.BSP` | Mundo RenderWare (chunk 0x0B) da pista |
| `.SPL` | Texto, `CurveGraph`: traçado da IA (`AIGuidanceSpline`) e grid de largada |
| `.CAM` | XML com as câmeras da pista |
| `.MAP`, `.SCN`, `.ENV`, `.FOG`, `.CLN`, `.GLW` | Texto estilo INI: minimapa, cena, iluminação, neblina etc. |
| `.ADJ`, `.PVS`, `.BUF` | Binários da pista ainda não analisados |

Cada pista (`TRACKS\<PISTA>.MIX`) traz versões de seca, nublado, molhado e
chuva da mesma cena.
