# Formato `MOTOGP.DAT` (MotoGP 4, PS2, SLUS-21159)

Pacote único da Namco com quase todos os dados do jogo (397 MB). Validado na
ISO americana: os 1.158 arquivos compactados descompactam exatamente no
tamanho esperado. Ferramenta: `tools/gp4dat.py`.

Todos os inteiros são little-endian.

## Índice (dentro do executável)

O `.DAT` não tem índice próprio. A tabela fica no executável `SLUS_211.59`, no
endereço virtual `0x3FDFC0` (offset `0x2FEFC0` no arquivo), com 1.489 entradas
de 36 bytes:

| Offset | Tipo | Conteúdo |
| ------ | ---- | -------- |
| 0x00   | u32  | ponteiro (endereço virtual) para o nome, string ASCII terminada em `\0` |
| 0x04   | u32  | setor inicial no `.DAT` (setor = 2048 bytes) |
| 0x08   | u32  | 16 bits baixos: quantidade de setores ocupados. 16 bits altos: desconhecido |
| 0x0C   | u32  | desconhecido |
| 0x10   | u32  | tamanho compactado em bytes (0 = sem compressão) |
| 0x14   | u32  | tamanho descompactado em bytes (0 quando não há compressão) |
| 0x18   | 12 B | zeros |

A ferramenta localiza a tabela sozinha (a maior sequência de entradas
válidas), então deve funcionar em outras versões do executável.

Arquivos sem compressão ocupam os setores inteiros (o tamanho exato não está
na tabela). Arquivos compactados ficam **alinhados ao fim** da área de setores:
começam em `setor * 2048 + setores * 2048 - tamanho_compactado`.

## Compressão (LZ da Namco)

Sequência de tokens de 2 bytes `b0 b1`:

- `b1 == 0xFF`: copiar os próximos `b0 + 1` bytes literalmente.
- Caso contrário, `v = b0 | (b1 << 8)` é uma referência para trás: copiar
  `(v & 0x1F) + 3` bytes a partir de `(v >> 5) + 1` bytes atrás na saída (a
  cópia pode se sobrepor).

## O que há dentro (resumo)

- Os nomes não têm extensão: `CourseJerez`, `CourseJerezR` (traçado invertido),
  `CourseJerez_Free`, `bike_motogp_for_46`, `bike_motogp_for_46_sl`,
  `rider_motogp_m_46`, `helmet_motogp_agt_46` etc.
- Pistas: Suzuka, Jerez, Motegi, Donington, Catalunya, Assen, Sachsenring,
  Mugello, Le Mans, Brno, Estoril, Valencia, Phillip Island, Sepang, Qatar,
  além de Paul Ricard (`Paul`), Welkom (`Welcom`), `Nelson` e `Training`. Cada
  uma tem a versão invertida (`...R`).
- Modelos 3D (pistas e motos) usam o formato próprio da Namco `OBJ10001`.
  As texturas usam `TEX10001`. Nenhum dos dois foi analisado ainda.
