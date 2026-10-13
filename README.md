# MotoGP 08 + MotoGP 4 (PS2)

Mod de PS2 que usa o **MotoGP 08** (Milestone/Capcom, 2008) como base e traz as
**motos e pistas do MotoGP 4** (Namco, 2005).

- **Alvo:** XBSX2 (versão do PCSX2 para Xbox) e PCSX2.
- **Entrega:** uma ISO modificada do MotoGP 08, distribuída como patch (xdelta)
  aplicado sobre a ISO original de cada jogador.

## Desafio principal

Os dois jogos são de estúdios diferentes e usam engines diferentes. Por isso,
nenhum arquivo do MotoGP 4 funciona direto no MotoGP 08: cada tipo de dado
(modelo 3D, textura, colisão, traçado da IA) precisa ser decodificado nos dois
jogos e convertido de um formato para o outro.

## Fases

| Fase | Objetivo | Status |
| ---- | -------- | ------ |
| 0 | Mapear os arquivos das duas ISOs (pacotes, compressão, onde ficam motos e pistas) | aguardando ISOs |
| 1 | Desempacotar e reempacotar os arquivos do MotoGP 08 sem quebrar o jogo | — |
| 2 | Trocar texturas e pinturas das motos (primeiro resultado visível) | — |
| 3 | Converter os modelos 3D das motos do MotoGP 4 para o formato do MotoGP 08 | — |
| 4 | Pistas: visual, colisão, traçado da IA, câmeras e cronometragem | — |

A fase 4 é a mais difícil. Uma pista não é só o visual: o jogo precisa da
colisão, do traçado que a IA segue, dos pontos de largada, dos setores de
cronometragem e das câmeras.

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
```

A saída de `summary` e de `list --magic` é só texto e já basta para começar a
identificar os formatos, sem precisar enviar a ISO inteira.

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
