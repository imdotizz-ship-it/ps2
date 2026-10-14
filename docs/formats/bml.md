# Formato `.BML` (MotoGP 08, Milestone)

XML em binário: as configurações do jogo (`DATA\AIPARAMS.BML`,
`DATA\CAMERAS.BML`, `DATA\DB_*.BML`, os `.BML` das pistas). Nomes e valores
ficam em UTF-32. Ferramenta: `tools/bml.py` (lê, edita e regrava; os 172
`.BML` de `DATA.MIX` saem byte a byte iguais ao regravar sem mudanças).

Todos os inteiros são u32 little-endian.

## Arquivo

| Offset | Conteúdo |
| ------ | -------- |
| 0x00 | 0 |
| 0x04 | 12 (o nó raiz começa em 0x04 + 12 = 0x10) |
| 0x08 | número total de nós (elementos e textos) |
| 0x0C | 0 |
| 0x10 | nó raiz |

O arquivo termina sem a última palavra zero do nó raiz.

## Nó

Cabeçalho de 9 palavras (0x24 bytes):

| Palavra | Conteúdo |
| ------- | -------- |
| 0 | 0x24 |
| 1 | tamanho do nó, com os filhos |
| 2 | tipo: 1 elemento, 3 texto |
| 3 | texto: offset do valor (relativo ao nó); o tamanho em bytes fica na palavra anterior ao valor |
| 4 | número de atributos |
| 5 | offset do primeiro atributo, apontando logo depois da palavra de tamanho do registro |
| 6 | número de filhos |
| 7 | offset do primeiro filho |
| 8 | tamanho do nome em bytes (UTF-32 com o `\0`) |

Depois vêm o nome; os atributos (tamanho do registro, 0, tamanho do nome,
nome, tamanho do valor, valor); no nó de texto, o tamanho e o valor; uma
palavra zero; e os filhos.

O texto de um elemento é um filho do tipo 3 chamado `text`:
`<fFocal>70</fFocal>` vira o elemento `fFocal` com um filho `text` = `"70"`.

## Arquivos usados pelos mods

- `DATA\AIPARAMS.BML`: comportamento da IA. Em `General`, `Brake`,
  `Overtake` e `Defense` ficam as distâncias de desvio e as "caixas" de
  colisão que fazem um bot frear ou desviar de outro.
- `DATA\CAMERAS.BML`: câmeras da corrida. `GAME index=N` é a lista do botão
  de trocar câmera (cada valor é o `index` de um `CAMERA`). Cada `CAMERA` tem
  `eMode` (`MODE_INSIDE`, `MODE_REAR_NEAR`, `MODE_REAR_FAR`, `MODE_BONNET`,
  `MODE_RIDER_FELL`), `vCameraPos` (posição em relação à moto, em metros:
  lado, altura, frente), `vCameraDir` (direção do olhar) e `fFocal`.
- `DATA\DB_CHEATS.BML`: os cheats do jogo (`big_head`, `brake`, `drift`,
  `grip`, `speed`).
