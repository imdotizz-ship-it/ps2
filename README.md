# MotoGP 08 + MotoGP 4 (PS2)

Mod de PS2 que usa o **MotoGP 08** (Milestone/Capcom, 2008) como base e traz as
**motos e pistas do MotoGP 4** (Namco, 2005), com bots mais agressivos e uma
câmera de TV a mais.

- **Alvo:** XBSX2 (versão do PCSX2 para Xbox) e PCSX2.
- **Entrega:** a ISO modificada é montada a partir da ISO original de cada
  jogador, por uma página que funciona no navegador do iPhone, Android ou PC.

## Como instalar (iPhone, Android ou PC)

1. Tenha a ISO original **MotoGP 08 (USA)** no aparelho (app Arquivos no
   iPhone).
2. Abra no navegador:
   **https://raw.githack.com/imdotizz-ship-it/ps2/claude/ps2-game-mods-drastic-3mwmob/patcher/index.html**
3. Escolha a ISO, toque em **Criar ISO** e depois em **Salvar**. A página
   baixa só o patch (algumas dezenas de MB); a ISO não sai do aparelho.

No iPhone precisa do iOS 16.4 ou mais novo, e a tela deve ficar ligada até
terminar. A ISO nova vai para a pasta Downloads do app Arquivos.

## O que muda

| Mod | Detalhes |
| --- | -------- |
| Motos do MotoGP 4 | As seis motos da MotoGP com carenagem, quadro, motor, escapamento, para-brisa e pinturas do MotoGP 4 ([detalhes](#motos-do-motogp-4-no-motogp-08)) |
| Pistas do MotoGP 4 | Brno, Catalunya, Doha, Donington, Estoril, Jerez, Mugello, Phillip Island, Sachsenring, Sepang e Valência com o visual do MotoGP 4 ([detalhes](docs/formats/pistas.md)) |
| Bots mais agressivos | Os pilotos da CPU guardam metade da distância uns dos outros: o dobro de toques e quedas entre eles |
| Câmera de TV | O botão de trocar câmera ganha uma câmera alta, atrás e acima da moto, no lugar da segunda câmera de cockpit |

Nas pistas, colisão, traçado da IA, grid, câmeras de replay e cronometragem
continuam as do MotoGP 08, então as corridas funcionam normalmente; muda o
que se vê. Assen, Le Mans e Motegi continuam com o visual do 08 (veja o
porquê em [pistas](docs/formats/pistas.md#resultado)), e Indianápolis, Laguna
Seca, Misano e Xangai não existem no MotoGP 4.

**Ainda não testado em emulador nem console.** Tudo foi validado só
remontando e relendo os arquivos e por prévias renderizadas aqui. O risco
maior são as pistas: o cenário novo tem até o dobro de triângulos do
original e o jogo carrega a versão `.SLF` em vez da pré-compilada `.SLI`. Se
uma pista travar ao carregar, dá para gerar o patch com menos triângulos
(`--budget` em `tools/tracks4to08.py`).

## Desafio principal

Os dois jogos são de estúdios diferentes e usam engines diferentes. Por isso,
nenhum arquivo do MotoGP 4 funciona direto no MotoGP 08: cada tipo de dado
(modelo 3D, textura, colisão, traçado da IA) precisa ser decodificado nos dois
jogos e convertido de um formato para o outro.

## Fases

| Fase | Objetivo | Status |
| ---- | -------- | ------ |
| 0 | Mapear os arquivos das duas ISOs (pacotes, compressão, onde ficam motos e pistas) | Concluída: `.MIX` do MotoGP 08 ([formato](docs/formats/mix.md)) e `MOTOGP.DAT` do MotoGP 4 ([formato](docs/formats/gp4dat.md)) abertos |
| 1 | Desempacotar e reempacotar os arquivos do MotoGP 08 sem quebrar o jogo | Concluída |
| 2 | Trocar texturas e pinturas das motos | Concluída junto com a fase 3 |
| 3 | Converter os modelos 3D das motos do MotoGP 4 para o formato do MotoGP 08 | Concluída |
| 4 | Pistas: visual do MotoGP 4 sobre colisão, IA, câmeras e cronometragem do 08 | Concluída em 11 das 14 pistas em comum |
| 5 | Jogabilidade: IA, câmeras | IA e câmera de TV por dados ([BML](docs/formats/bml.md)). Câmera livre com L1+R1: não feita (exige mudar o código do jogo; veja abaixo) |

Câmera livre: o MotoGP 08 já tem uma câmera que gira em volta da moto no
**Replay** (modo Orbit). Uma câmera livre durante a corrida, ligada por
L1+R1, exige alterar o executável do jogo, e isso não dá para fazer com
segurança sem um emulador para testar.

## Patches

O patch completo fica em `patcher/` (página `index.html`, `manifest.json` e as
partes `part-NN.patch`), aplicado pela página acima ou no PC com
`python3 tools/isopatch.py apply "MotoGP 08 (USA).iso" patcher saida.iso`. Ele
parte da ISO original **MotoGP 08 (USA)** (SHA-1
`25cdef00791ac502dfad8a21b1f39b64b58fc361`) e confere a ISO final por SHA-1.

Os patches xdelta antigos continuam valendo (Delta Patcher, UniPatcher ou
`xdelta3 -d -s "MotoGP 08 (USA).iso" PATCH.xdelta SAIDA.iso`):

| Patch | O que faz | SHA-1 da ISO resultante |
| ----- | --------- | ----------------------- |
| `patches/teste-moto-azul.xdelta` | Teste do fluxo: a moto vermelha do primeiro slot (BIKE01) fica azul | `854013d5cbc693ccd9241ebbd30044493f08ef3b` |
| `patches/motos-motogp4.xdelta` | Só as motos do MotoGP 4 | `67dbe53613467e9696ee0e14a79cbae4a7f404fc` |

### Motos do MotoGP 4 no MotoGP 08

![As seis motos convertidas](docs/motos-motogp4.png)

Cada modelo do 08 atende duas ou três equipes e recebeu uma moto do MotoGP 4
do mesmo fabricante:

| Modelo do 08 | Equipes no 08 | Moto do MotoGP 4 |
| ------------ | ------------- | ---------------- |
| BIKE01 | Ducati Marlboro, Alice | Ducati #65 (Capirossi) |
| BIKE02 | Rizla Suzuki | Suzuki #21 (Hopkins) |
| BIKE03 | Kawasaki | Kawasaki #56 (Nakano) |
| BIKE04 | Repsol Honda | Repsol Honda #69 (Hayden) |
| BIKE05 | Fiat Yamaha, Tech 3 | Gauloises Yamaha #46 (Rossi) |
| BIKE06 | Hondas satélites (Gresini, LCR, JiR) | Movistar Honda #15 (Gibernau) |

O que muda: carenagem, quadro, motor, escapamento, rabeta, painel e
para-brisa (com os dois níveis de detalhe). Rodas, garfo, balança, guidão e
corrente continuam os do 08, então a física e as animações do piloto não
mudam. As placas de número do 08 ficam escondidas, porque as pinturas do
MotoGP 4 já trazem os números. Todas as equipes do mesmo modelo usam a mesma
moto do MotoGP 4, já que no 08 a geometria é compartilhada por modelo.

Para refazer (ou escolher outras motos, com `--map BIKE05=tec_17` por exemplo):

```sh
pip install numpy pillow
python3 tools/ps2iso.py extract "MotoGP 08 (USA).iso" extracted/mgp08 BIKES.MIX
python3 tools/ps2iso.py extract "MotoGP 4 (USA).iso" extracted/mgp4 'SLUS_211.59' MOTOGP.DAT
python3 tools/gp4dat.py extract extracted/mgp4/SLUS_211.59 extracted/mgp4/MOTOGP.DAT extracted/mgp4_x
python3 tools/bikes4to08.py build extracted/mgp08/BIKES.MIX extracted/mgp4_x build
python3 tools/ps2iso.py replace "MotoGP 08 (USA).iso" build/mgp08_m4bikes.iso BIKES.MIX=build/BIKES.MIX
python3 tools/bikes4to08.py preview build/BIKES.MIX build/preview.png   # confere sem emulador
```

Para refazer o patch de teste a partir dos arquivos extraídos:

```sh
python3 tools/rwtxd.py recolor BIKES/BIKE01/PICTURES/BIKE01.TXD BIKE01.TXD bgr 'CHASSIS*'
python3 tools/mix.py replace BIKES.MIX BIKES_mod.MIX 'BIKES\BIKE01\PICTURES\BIKE01.TXD=BIKE01.TXD'
python3 tools/ps2iso.py replace "MotoGP 08 (USA).iso" teste.iso BIKES.MIX=BIKES_mod.MIX
```

## ISOs usadas

| Jogo | Serial | Tamanho | SHA-1 |
| ---- | ------ | ------- | ----- |
| MotoGP 08 (USA) | SLUS-21811 | 1.631.027.200 | `25cdef00791ac502dfad8a21b1f39b64b58fc361` |
| MotoGP 4 (USA) | SLUS-21159 | 1.239.285.760 | `d9bb4666d57a86ddbba6ab985ea0e12e8a55c843` |

## Ferramentas

### `tools/ps2iso.py`

Lê ISOs de PS2 usando só o Python padrão (3.8+), sem instalar nada. Funciona com
`.iso` (DVD) e com `.bin` raw de 2352 bytes (CD).

```sh
python3 tools/ps2iso.py info    MotoGP08.iso                 # serial do jogo e resumo
python3 tools/ps2iso.py summary MotoGP08.iso                 # tipos de arquivo por extensão e assinatura
python3 tools/ps2iso.py list    MotoGP08.iso --magic         # todos os arquivos + primeiros bytes
python3 tools/ps2iso.py extract MotoGP08.iso extracted/mgp08 # extrai tudo
python3 tools/ps2iso.py extract MotoGP08.iso extracted/mgp08 'DATA/*.PAK'  # só o que casar com o padrão
python3 tools/ps2iso.py replace MotoGP08.iso MotoGP08_mod.iso BIKES.MIX=BIKES_mod.MIX  # troca arquivos
```

A saída de `summary` e de `list --magic` é só texto e já basta para começar a
identificar os formatos, sem precisar enviar a ISO inteira.

`replace` gera uma cópia da ISO com arquivos trocados. Se o arquivo novo
couber nos setores do antigo, ele é gravado no mesmo lugar; se não, vai para o
fim da imagem.

### `tools/mix.py`

Lista, extrai e remonta os pacotes `.MIX` do MotoGP 08, já com os nomes
decifrados. Remontar sem mudanças gera um arquivo idêntico ao original (testado
nos 33 pacotes).

```sh
python3 tools/mix.py list    extracted/mgp08/BIKES.MIX
python3 tools/mix.py extract extracted/mgp08/TRACKS/JEREZ.MIX extracted/mgp08_x
python3 tools/mix.py extract extracted/mgp08/TRACKS/JEREZ.MIX extracted/mgp08_x 'TRACKS\JEREZ\*.SPL'
python3 tools/mix.py replace extracted/mgp08/BIKES.MIX BIKES_mod.MIX 'BIKES\BIKE01\PICTURES\BIKE01.TXD=novo.TXD'
```

### `tools/rwtxd.py`

Lista as texturas de um `.TXD` (RenderWare de PS2) e recolore as paletas,
trocando os canais de cor. Usado no patch de teste.

### `tools/bikes4to08.py` e `tools/mgp4to08/`

Conversor das motos do MotoGP 4 para o MotoGP 08 (veja acima). Precisa de
`numpy` e `Pillow`. Os módulos em `tools/mgp4to08/` leem os modelos e as
texturas dos dois jogos ([SLF/TXD do 08](docs/formats/slf.md),
[OBJ10001/TEX10001 do MotoGP 4](docs/formats/obj10001.md)) e gravam
RenderWare. Também têm um rasterizador simples para gerar prévias.

`tools/mix.py replace` ganhou `--rename OLD=NEW` (precisa vir depois dos
`NAME=FILE`), usado para esconder o `.SLI` de um modelo.

### `tools/gp4dat.py`

Lista e extrai o `MOTOGP.DAT` do MotoGP 4, já descompactado. Precisa do
executável do jogo, onde fica o índice.

```sh
python3 tools/gp4dat.py list    extracted/mgp4/SLUS_211.59 extracted/mgp4/MOTOGP.DAT
python3 tools/gp4dat.py extract extracted/mgp4/SLUS_211.59 extracted/mgp4/MOTOGP.DAT extracted/mgp4_x 'CourseJerez*'
```

### `tools/tracks4to08.py`

Converte uma pista do MotoGP 4 para o `.MIX` da mesma pista no MotoGP 08
([como funciona](docs/formats/pistas.md)). Precisa de `numpy`, `scipy` e
`Pillow`.

```sh
python3 tools/tracks4to08.py build   extracted/mgp08/TRACKS/JEREZ.MIX extracted/mgp4_x build/tracks
python3 tools/tracks4to08.py preview build/tracks/JEREZ.MIX build/jerez.png   # seis vistas do piloto
```

### `tools/data08.py` e `tools/bml.py`

`data08.py` aplica os mods de jogabilidade (IA e câmera de TV) no `DATA.MIX`.
`bml.py` lê e edita os `.BML` do jogo ([formato](docs/formats/bml.md)).

```sh
python3 tools/data08.py extracted/mgp08/DATA.MIX build
python3 tools/bml.py dump extracted/mgp08_x/DATA/AIPARAMS.BML
```

### `tools/isopatch.py`

Gera e aplica o patch da pasta `patcher/`: o que é igual à ISO original é
copiado dela, e só os dados novos ficam no patch, compactados. A página
`patcher/index.html` faz a mesma montagem no navegador, sem carregar a ISO
inteira na memória.

```sh
python3 tools/isopatch.py make  "MotoGP 08 (USA).iso" patcher BIKES.MIX=build/BIKES.MIX DATA.MIX=build/DATA.MIX TRACKS/JEREZ.MIX=build/tracks/JEREZ.MIX ...
python3 tools/isopatch.py apply "MotoGP 08 (USA).iso" patcher saida.iso
```

### Refazer o patch completo

```sh
pip install numpy scipy pillow
python3 tools/ps2iso.py extract "MotoGP 08 (USA).iso" extracted/mgp08
python3 tools/ps2iso.py extract "MotoGP 4 (USA).iso" extracted/mgp4 'SLUS_211.59' MOTOGP.DAT
python3 tools/gp4dat.py extract extracted/mgp4/SLUS_211.59 extracted/mgp4/MOTOGP.DAT extracted/mgp4_x
python3 tools/bikes4to08.py build extracted/mgp08/BIKES.MIX extracted/mgp4_x build
python3 tools/data08.py extracted/mgp08/DATA.MIX build
for t in BRNO CATALUN DOHA DONNING ESTORIL JEREZ MUGELLO PHILLIPI SACHSEN SEPANG VALENCIA; do
  python3 tools/tracks4to08.py build extracted/mgp08/TRACKS/$t.MIX extracted/mgp4_x build/tracks
done
python3 tools/isopatch.py make "MotoGP 08 (USA).iso" patcher BIKES.MIX=build/BIKES.MIX DATA.MIX=build/DATA.MIX \
  $(for t in BRNO CATALUN DOHA DONNING ESTORIL JEREZ MUGELLO PHILLIPI SACHSEN SEPANG VALENCIA; do echo TRACKS/$t.MIX=build/tracks/$t.MIX; done)
```

## Regras do repositório

- Nunca faça commit de ISOs nem de arquivos extraídos dos jogos (o `.gitignore`
  já bloqueia os formatos comuns). Use apenas cópias dos seus próprios discos.
- O repositório guarda só ferramentas, scripts, documentação dos formatos e patches.

## Skills instaladas

- `.claude/skills/reverse-engineer-anything`: skill do
  [REA](https://github.com/morluto/rea) (licença MIT, commit `ca2d15b`). Ela
  orienta a análise de binários e depende do servidor MCP do REA e do Ghidra
  para funcionar por completo. A análise MIPS do REA só aceita ELFs MIPS32r2 e
  recusa variantes específicas de máquina, então os executáveis de PS2
  (Emotion Engine / R5900) não são suportados por ele. Para esses, o caminho é o
  Ghidra com uma extensão para o Emotion Engine.
