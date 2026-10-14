"""Put MotoGP 4 (Namco, PS2) bikes and tracks into MotoGP 08 (Milestone, PS2).

Modules:
  gs        PS2 GS memory swizzling (PSMCT32 <-> PSMT4/PSMT8)
  vif       VIF command parser
  mgp4obj   OBJ10001 packets (DMA/VIF) of MotoGP 4 models
  mgp4mesh  vertex/strip decoding of OBJ10001 meshes
  mgp4tex   TEX10001 textures and their ids
  texdb     texture id -> RGBA image
  m4bike    a MotoGP 4 bike body/windscreen in MotoGP 08 coordinates
  rw        RenderWare 3.7 binary stream reader/writer
  slf       Selene Scene File (.SLF) directory and object headers
  build08   RenderWare geometry/material building and SLF rebuilding
  ps2tex    PS2 native 8-bit RenderWare textures (decode, re-encode)
  convert   one MotoGP 4 bike -> one MotoGP 08 bike slot
  render    tiny software rasterizer for previews
  view08    assemble a MotoGP 08 bike or track scene (hierarchy + textures) for previews
  track4    MotoGP 4 track geometry (Course<Name>.bin strips)
  trktex    MotoGP 4 track textures (Course<Name>_Free.bin)
  rwworld   MotoGP 08 collision (.BSP RenderWare world) with terrain types
  align     fit of a MotoGP 4 track onto the 08 one (rotation, translation, heights)
  track08   new MotoGP 08 track scene, textures and texture settings
"""
