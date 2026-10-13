# Formato `.SLF` / `.SLI` (Selene Scene File, MotoGP 08 PS2)

Cenas 3D da engine "Selene" da Milestone (versão 2.05). Analisado nas motos
(`BIKES\BIKE0n\BIKE0n.SLF`), mas o mesmo formato vale para piloto, cockpit e
objetos das pistas. Código: `tools/mgp4to08/slf.py` e `build08.py`.

Todos os inteiros são little-endian.

## `.SLF` x `.SLI`

As duas versões existem para cada modelo e têm a mesma estrutura:

- `.SLF`: geometria RenderWare **genérica** (vértices, normais, UV,
  triângulos) e nomes legíveis (`CHASSIS@Bike01`).
- `.SLI`: a mesma cena já **instanciada para o PS2** (geometria nativa, flag
  `0x01000000`) e nomes trocados por hashes (`#b828:de65:2d15:`).

O carregador (`0x229410` no `SLUS_218.11`) monta o caminho e testa nesta
ordem: `.sli`, `.slf`, `.rws`, `.dff`, usando o primeiro que existir. Os
dois primeiros passam pela mesma função (`0x2242c0`). Portanto, para trocar
um modelo basta gravar um `.SLF` novo e esconder o `.SLI` (renomeado no
`.MIX`): o jogo cai no `.SLF` e instancia a geometria ao carregar.

## Cabeçalho (0x400 bytes)

Texto (`Selene Scene File`, `Version 2.05`, `Objects : n`, `Mask`, `UXID`),
seguido de lixo de memória do exportador até 0x400.

| Offset | Conteúdo |
| ------ | -------- |
| 0x400  | `SLF\0` |
| 0x408  | versão (0x100) |
| 0x40C  | número de entradas do diretório |
| 0x424  | diretório: entradas de 32 bytes |

Entrada do diretório: nome (20 bytes, ASCII), offset absoluto (u32), tamanho
(u32), tipo (u32). Tipos vistos:

| Tipo | Conteúdo |
| ---- | -------- |
| 0x0002 | `@_SCENE_HEADER_@` |
| 0x0003 | dummy (ponto de referência: `RiderPos`, `DUMMY_EXHAUST0`) |
| 0x0303 / 0x0403 | objeto com malha |
| 0x0102 | `@HIERARCHY_DATA@` |
| 0x0006 / 0x0106 | `@____MATLIST___@` e `Effect_n` (efeitos de material) |
| 0x0005 | `@_____UXID_____@` |
| 0xFEFE | entrada vazia |

## Objeto

| Offset | Tipo | Conteúdo |
| ------ | ---- | -------- |
| 0x00 | u32 | 0x50 |
| 0x04 | 8 B | UXID do objeto |
| 0x0C | u32 | flags (bit 0x100: objeto com LODs) |
| 0x14 | 12 f32 | matriz 3x3 (linhas) + translação, relativa ao pai |
| 0x44 | i32 | pai: índice na lista de objetos com malha (dummies não contam), -1 = raiz |
| 0x54 | u32 | tamanho do nome; o nome vem em seguida, terminado em `\0` |

Convenção de vetor-linha: `mundo = local · R + t`, e `R_mundo = R_local · R_pai`.

Depois do nome vem um **Atomic** RenderWare 3.7 (chunk 0x14, versão
`0x1C020037`) e alguns bytes finais que devem ser preservados. Objetos com LOD
(`CHASSIS`) têm, logo após o nome, dois u32 com o **offset absoluto no
arquivo** do bloco de cada LOD (um registro de 0x30 bytes seguido do Atomic do
LOD); ao reescrever o arquivo esses dois valores precisam ser recalculados.

### Hierarquia das motos

Unidades em metros, Y para cima, Z para a frente, eixo traseiro na origem
(0, 0,316, 0). `CHASSIS` é a raiz; `HANDLE` (direção, com a inclinação do
garfo) → `FRONT_SUSP` → `FRIM` → `FWHEEL`; `REAR_RAKE` (balança) → `RRIM` →
`RWHEEL`, `CHAIN`. `FGLASS` (para-brisa) e as placas `NUMBERA/B` são filhos
de outros nós e variam de moto para moto.

## Geometria RenderWare

Atomic → Geometry (0x0F) com struct, lista de materiais (0x08) e extensões:
`0x50E` (BinMesh: índices por material, obrigatório) e `0x11F` (UserData:
nome, informação de LOD). Materiais têm textura (0x06), MatFX (0x120, env map
`RTCubeEnvMap`), um chunk `0xFFFE` com o índice do `Effect_n` da cena e
UserData com o nome.

Flags usadas pelo jogo: `0x10077` (strips, posições, UV, normais, luz),
`0x1003F` (com cor por vértice, objetos de pista), `0x1000F` (cor por vértice
sem luz). As motos convertidas usam `0x1005E`: lista de triângulos, cor por
vértice e sem iluminação dinâmica, igual ao visual original do MotoGP 4.

A face da frente segue `cross(v1 - v0, v2 - v0)` apontando para fora (mesmo
sentido das normais). No struct da geometria cada triângulo é gravado como
`u16 v1, v0, material, v2`.

## `.TXS`

Texto com uma linha por textura: nome (coluna 1) e flags a partir da coluna
37 (`L` trava, `K` color key, `T5A128` teste de alfa ≥ 128 etc.). Texturas
novas são acrescentadas no fim.

## `.TXD`

Dicionário de texturas RenderWare com rasters nativos de PS2: 8 bits com
paleta (8888 ou 1555). Cada raster traz dois pacotes GIF (pixels e paleta),
com `TRXREG` em +0x20. Os pixels PSMT8 são enviados como PSMCT32 de metade da
largura e metade da altura, ou seja, ficam "embaralhados" na ordem da memória
do GS. A paleta de 256 cores usa a ordem CSM1 (troca dos bits 3 e 4 do
índice). O alfa da paleta vai de 0 a 0x80. Código: `tools/mgp4to08/ps2tex.py`
e `gs.py`.

Cada modelo atende duas ou três equipes: `CHASSISA_0` / `CHASSISB_0` /
`CHASSISC_0` são as pinturas e `NUMBERA_n` / `NUMBERB_n` os números.
