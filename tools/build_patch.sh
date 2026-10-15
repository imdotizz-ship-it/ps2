#!/bin/bash
# Rebuild patcher/ (the complete patch) from the two original ISOs.
#   tools/build_patch.sh "MotoGP 08 (USA).iso" "MotoGP 4 (USA).iso" [WORK_DIR]
# Needs Python 3.8+ with numpy, scipy and Pillow; takes about an hour (the tracks).
set -e
ISO08=$1; ISO4=$2; W=${3:-build}
[ -f "$ISO08" ] && [ -f "$ISO4" ] || { echo "usage: $0 MOTOGP08.iso MOTOGP4.iso [WORK_DIR]"; exit 1; }
T=$(dirname "$0")
TRACKS="BRNO CATALUN DOHA DONNING ESTORIL JEREZ MUGELLO PHILLIPI SACHSEN SEPANG VALENCIA"
FOVS="60 65 70 75 80 85 90 95 100 105 110"
python3 $T/ps2iso.py extract "$ISO08" $W/mgp08 BIKES.MIX DATA.MIX MENU.MIX SFX.MIX SLUS_218.11 'TRACKS/*.MIX'
python3 $T/mix.py extract $W/mgp08/MENU.MIX $W/font 'MENU\FONT\HELVETICANEUE_LT_65_MEDIUM24.*'
python3 $T/hooks/gen_font.py $W/font/MENU/FONT/HELVETICANEUE_LT_65_MEDIUM24.PNG $W/font/MENU/FONT/HELVETICANEUE_LT_65_MEDIUM24.MET $T/hooks/font_atlas.h
python3 $T/hooks/build_hook.py $W/mgp08/SLUS_218.11 $W/hooks/SLUS_218.11   # needs clang + ld.lld (MIPS)
python3 $T/audio/sfx08.py $W/mgp08/SFX.MIX $W/sfx
python3 $T/hooks/make_fov_text.py $W/mgp08/MENU.MIX $W/hooks/MENU.MIX
python3 $T/ps2iso.py extract "$ISO4" $W/mgp4 SLUS_211.59 MOTOGP.DAT
python3 $T/gp4dat.py extract $W/mgp4/SLUS_211.59 $W/mgp4/MOTOGP.DAT $W/mgp4_x
python3 $T/bikes4to08.py build $W/mgp08/BIKES.MIX $W/mgp4_x $W/bikes
python3 $T/safetycar.py $W/bikes/BIKES.MIX $W/mgp4_x $W/safetycar --template $W/mgp08/BIKES.MIX
for t in $TRACKS; do python3 $T/tracks4to08.py build $W/mgp08/TRACKS/$t.MIX $W/mgp4_x $W/tracks; done
for f in $FOVS; do
  python3 $T/data08.py $W/mgp08/DATA.MIX $W/data/fov$f --fov $f
  python3 $T/data08.py $W/mgp08/DATA.MIX $W/data/sc$f --fov $f --safety-car
done
TR=""; for t in $TRACKS; do TR="$TR TRACKS/$t.MIX=$W/tracks/$t.MIX"; done
OPT=""; SC="BIKES.MIX=$W/safetycar/BIKES.MIX"
for f in $FOVS; do OPT="$OPT,$f:DATA.MIX=$W/data/fov$f/DATA.MIX"; SC="$SC,@$f:DATA.MIX=$W/data/sc$f/DATA.MIX"; done
rm -f $T/../patcher/manifest.json $T/../patcher/part-*.patch
python3 $T/isopatch.py make "$ISO08" $T/../patcher SLUS_218.11=$W/hooks/SLUS_218.11 MENU.MIX=$W/hooks/MENU.MIX BIKES.MIX=$W/bikes/BIKES.MIX DATA.MIX=$W/data/fov70/DATA.MIX SFX.MIX=$W/sfx/SFX.MIX \
  --name "MotoGP 08 + MotoGP 4.iso" \
  --note "Câmera livre: segure L1+R1 na corrida. Analógico esquerdo anda, direito olha, R2/L2 sobe/desce, quadrado rápido, X devagar, direcional cima/baixo muda o FOV, triângulo congela/solta a corrida" \
  --note "Campo de visão dentro do jogo: Opções > Video Setup > Field of view, de -5° a +40° sobre o FOV escolhido aqui" \
  --note "Motion blur forte acima de 90 km/h, cada vez mais forte até 270 km/h" \
  --note "Takedown estilo Burnout 3: quando você derruba um piloto, a câmera corta para a queda dele em câmera lenta por uns 4 segundos enquanto o piloto automático guia a sua moto" \
  --note "Xingamentos: quem cai depois de um toque xinga o rival numa caixa no estilo do HUD do jogo, com voz em português" \
  --note "Sangue e destroços nas quedas: jato de sangue que forma poças e peças da moto voando; numa queda forte o para-brisa daquela moto quebra e some até o fim da corrida" \
  --note "Briga: às vezes, quando um bot derruba outro, a câmera corta para ele sacudindo o punho (gesto de raiva do jogo) em câmera lenta, com o xingamento na tela" \
  --note "Quedas fatais: numa queda forte (acima de ~90 km/h) um piloto da IA pode morrer (1 em 3); a corrida recebe bandeira vermelha e para, e o START abre o menu para reiniciar" \
  --note "Torcida e som ambiente mais altos (cerca de 4 dB a mais, sem estourar)" \
  --note "Motos do MotoGP 4 nas seis motos da MotoGP" \
  --note "Bots com o dobro de chance de cair e menos cuidado entre si" \
  --note "Todos os pilotos da IA com o ritmo do mais rápido da categoria e todas as motos com o torque da mais forte: o grid inteiro briga pela vitória, ataca de mais longe e defende sem tirar o pé" \
  --note "Toques derrubam mais fácil e empurram mais forte (estilo takedown); rivalidades crescem mais rápido a cada batida" \
  --note "Câmera de TV no botão de trocar câmera, tremor da câmera em alta velocidade e efeito de velocidade mais cedo" \
  --note "Câmera Orbit do replay quase livre (gira de baixo até em cima da moto)" \
  --option fov "Campo de visão (FOV) das câmeras da moto" 70 "${OPT:1}" --option-unit "°" \
  --option-note "70° é o original. Vale para as câmeras de corrida; para mudar depois, monte a ISO de novo." \
  --profile safetycar "Safety Car do MotoGP 4 como equipe extra (experimental)" \
    "A BMW M6 Safety Car entra como uma equipe e um piloto a mais. Ela anda com a física de moto da Honda (inclina nas curvas), tem colisão do tamanho do carro, e aparece com os nomes da Repsol Honda e do Hayden porque o jogo não tem textos para ela. Pode travar o jogo nos menus: se travar, monte a ISO sem esta opção." \
    "$SC"
