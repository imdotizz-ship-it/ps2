"""Put MotoGP 4 (Namco, PS2) bikes into MotoGP 08 (Milestone, PS2).

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
  view08    assemble a MotoGP 08 bike (hierarchy + textures) for previews
"""
