# Pistas: MotoGP 4 → MotoGP 08

Código: `tools/tracks4to08.py` e `tools/mgp4to08/` (`track4`, `trktex`,
`rwworld`, `align`, `track08`).

## O que fica de cada jogo

Do MotoGP 08 ficam a colisão (`.BSP`, mundo RenderWare com o tipo de terreno
de cada triângulo: `TARMAC`, `CORDOLO`, `GRASS`, `SAND`, `TARMACPIT`), o
traçado da IA e o grid (`.SPL`), câmeras de TV, visibilidade (`.PVS`), luzes
e céu. Por isso corrida, cronometragem e IA funcionam como no 08.

Do MotoGP 4 vem o visual: os objetos do cenário do 08 (setores
`..._Sector_X_Y@`, tipos 0x103 opaco e 0x203 recortado) recebem os
triângulos do MotoGP 4 que caem no mesmo setor. A ordem e os nomes dos
objetos não mudam, então o `.PVS` continua valendo. A cópia pré-compilada
(`.SLI`) é renomeada para `.SLX` para o jogo carregar o `.SLF` novo.

## Dados do MotoGP 4

- `Course<Nome>.bin`: o primeiro bloco `OBJ10001` tem a pista inteira em
  tiras de triângulos ([formato](obj10001.md)). Tiras de "mundo" já vêm em
  coordenadas da pista: V3-32 posição, V2-32 uv (bit 0 de u = ADC), V4-8 cor
  com alfa (0x80 = 1,0). O cabeçalho do lote diz a textura (índice na lista
  do pacote) e se a tira é mesclada (`flags[0] = 1`); nas mescladas, o alfa
  do vértice é o peso da mistura (sombras, tintas, transições de terreno).
- `Course<Nome>_Free.bin`: as texturas (`TEX10001` com registros lineares
  PSMT4/PSMT8, mipmaps). A lista de IDs do cabeçalho usa saltos: `8xxx` =
  próximo ID, byte alto = salto, e `Axxx` = salto de 12 bits para a entrada
  seguinte (ex.: `A7C9` = +1993). Sem o salto de 12 bits, dezenas de texturas
  ficam com o ID errado (o asfalto de Doha, os boxes de Jerez).
- O céu (meia esfera de 1,3 km) e os painéis de fundo são descartados: o
  08 desenha o próprio céu.

## Encaixe

1. Orientação inicial: correlação (FFT) entre a linha da IA do 08 e um campo
   de distância dos vértices do MotoGP 4, em ângulos de 2°. As 4 melhores
   orientações seguem para o passo 2.
2. Asfalto do MotoGP 4: entre as texturas sob a linha da IA, a que melhor
   casa com o asfalto (`TARMAC`) do 08 depois de um ICP com rotação,
   translação e escala (limitada a ±5%). A nota é a média harmônica entre o
   quanto do asfalto do 08 fica a menos de 2 m do asfalto do MotoGP 4 e
   vice-versa.
3. Deformação suave no plano (malha de 16 m), puxando o asfalto do MotoGP 4
   para cima do asfalto do 08: os circuitos da Namco não são réplicas
   exatas (Doha precisou de até 8,6 m).
4. Correção de altura suave (malha de 8 m) e o terreno do MotoGP 4
   assentado na colisão do 08. Onde há duas camadas de colisão (pontes),
   vale a mais próxima. Triângulos muito maiores que o resto da sua tira
   (ligações espúrias entre peças) são descartados, e nas camadas mescladas
   o alfa do vértice entra no teste de alfa do 08.
5. Onde a colisão do 08 não tem chão do MotoGP 4 por cima, os triângulos da
   colisão viram chão, com a textura do MotoGP 4 mais comum naquele tipo de
   terreno, 5 cm abaixo.
6. Limite de triângulos (padrão: o dobro da cena do 08): saem primeiro os
   detalhes pequenos e distantes; o chão a até 12 m do asfalto nunca sai.

`tracks4to08.py build` mostra a nota do asfalto e a cobertura final, e
avisa quando a cobertura fica abaixo de 40%.

## Resultado

| Pista | Asfalto coberto | Situação |
| ----- | --------------- | -------- |
| Brno | 77% | convertida |
| Catalunya | 76% | convertida |
| Doha | 52% | convertida (as áreas de escape asfaltadas do 08 não contam) |
| Donington | 79% | convertida |
| Estoril | 95% | convertida |
| Jerez | 84% | convertida |
| Mugello | 79% | convertida |
| Phillip Island | 74% | convertida |
| Sachsenring | 84% | convertida |
| Sepang | 93% | convertida |
| Valência | 85% | convertida |
| Assen | 16% | mantida a do 08: o traçado mudou em 2006 |
| Le Mans | 24% | mantida a do 08: o modelo do MotoGP 4 não encaixa |
| Motegi | 94% | mantida a do 08: a pista oval passa por cima do traçado e as alturas não fecham |

Indianápolis, Laguna Seca, Misano e Xangai não existem no MotoGP 4.
