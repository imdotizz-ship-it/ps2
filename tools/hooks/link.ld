ENTRY(hook_input_update)
SECTIONS {
  . = 0x859f80;
  .mailbox : { KEEP(*(.mailbox)) }
  .text : { *(.text.hooks) *(.text*) __text_end = .; }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) *(.sdata*) }
  .bss : { *(.sbss*) *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.pdr) *(.comment) *(.gnu.attributes) }
}
