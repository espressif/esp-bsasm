// SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
// SPDX-License-Identifier: Apache-2.0
//
// BitScrambler assembly language (bsasm) — ANTLR4 grammar.
//
// This file is the single source of truth for the *syntax* of the language.
// It is intentionally free of target-language actions and semantic
// predicates so the same spec can later drive ANTLR targets for other
// languages. Everything that needs a readable diagnostic instead of a
// generic parse error - numeric ranges, label resolution, ctrsel/lutsel/
// rel_addr conflicts, extra instructions - is checked by the
// assembler (src/bsasm/sema.py); see the repository README.md for the full
// picture and for the 'how to add an instruction' walkthrough.
//
// Design notes
// ------------
// * Newlines are significant: an instruction bundle ends at a newline that
//   is not preceded by a comma. Comma-continuation across blank lines is
//   expressed by (COMMA NEWLINE* subInstr)*. A source file always ends with
//   a newline: the driver appends one if missing (the file may then end
//   inside a comment or after a label), so every rule can rely on NEWLINE
//   terminating a line.
// * The counter (A/B) and half (H/L) selectors are part of the mnemonic
//   tokens, not separate tokens: bare 'a', 'b', 'l' and 'h' are themselves
//   valid source bit names, so a standalone A/B/H/L token would make
//   'set 0 l' ambiguous. Keeping them in the mnemonic also means the
//   assembler never slices a mnemonic by character index.
// * AUX_CMP is a single token for comparator sources like 'bl<=o0'. In the
//   original assembler such a source had to be glued ('bl <= o0' with
//   spaces is a different - invalid - word), and only a single lexer token
//   can pin that without target-specific whitespace tricks.
// * REL_OPERAND ('l0+a', '0+a', bare '+a') is likewise one token: the '+a'
//   relative-addressing suffix must be glued to its base, and REL_OPERAND
//   being one token makes a spaced 'l0 +a' a syntax error rather than two
//   unrelated operands.
// * LABEL includes the colon and is matched by longest-match, so
//   'loopa:' is a label that happens to share a name with the LOOPA
//   mnemonic. References to keyword-shaped labels ('jmp set') work because
//   the `identifier` rule accepts every keyword token.
// * Numbers keep an optional sign in the token so that '-0x10' is one
//   integer (Python ``int(..., 0)``), not a stray '-' plus a hex word.
// * Keywords and word-shaped tokens are case-insensitive. ANTLR folds case
//   into the generated ATN at generation time, so the runtime needs no flag
//   and token text keeps its original spelling. Semantics still calls
//   .lower() where it compares names; that is independent of lexing.

grammar BitScrambler;

options { caseInsensitive = true; }

// ---------------------------------------------------------------------------
// Lexer
// ---------------------------------------------------------------------------

// A comment runs from '#' to the end of the line. The line terminator
// itself is not part of the comment and still terminates the statement.
COMMENT : '#' ~[\r\n]* -> channel(HIDDEN) ;

// Horizontal whitespace is insignificant. '\r' is deliberately NOT here:
// NEWLINE below accepts it, so LF, CRLF and lone-CR files all yield one
// NEWLINE per line with no special casing anywhere else.
WS : [ \t]+ -> skip ;

NEWLINE : '\r'? '\n' | '\r' ;

COMMA : ',' ;
RANGE : '..' ;

// 'cfg' statement keywords. Order matters only for equal-length matches:
// every keyword must be defined before NAME so that 'cfg' wins over
// NAME('cfg'), etc.
CFG : 'cfg' ;
LUT : 'lut' ;

K_PREFETCH        : 'prefetch' ;
K_TRAILING_BYTES  : 'trailing_bytes' ;
K_EOF_ON          : 'eof_on' ;
K_LUT_WIDTH_BITS  : 'lut_width_bits' ;
K_LOOP_ENDS_ON    : 'loop_ends_on' ;
K_EQUAL           : 'equal' ;
K_EQUAL_OR_GREATER: 'equal_or_greater' ;
K_UPSTREAM        : 'upstream' ;
K_DOWNSTREAM      : 'downstream' ;
K_TRUE            : 'true' ;
K_FALSE           : 'false' ;

// Instruction mnemonics.
SET   : 'set' ;
WRITE : 'write' ;
READ  : 'read' ;

LOOPA : 'loopa' ;
LOOPB : 'loopb' ;

ADDA : 'adda' ;  ADDAH : 'addah' ;  ADDAL : 'addal' ;
ADDB : 'addb' ;  ADDBH : 'addbh' ;  ADDBL : 'addbl' ;

IF  : 'if' ;
IFN : 'ifn' ;

LDCTDA : 'ldctda' ; LDCTDAH : 'ldctdah' ; LDCTDAL : 'ldctdal' ;
LDCTDB : 'ldctdb' ; LDCTDBH : 'ldctdbh' ; LDCTDBL : 'ldctdbl' ;

LDCTIA : 'ldctia' ; LDCTIAH : 'ldctiah' ; LDCTIAL : 'ldctial' ;
LDCTIB : 'ldctib' ; LDCTIBH : 'ldctibh' ; LDCTIBL : 'ldctibl' ;

ADDCTIA : 'addctia' ; ADDCTIAH : 'addctiah' ; ADDCTIAL : 'addctial' ;
ADDCTIB : 'addctib' ; ADDCTIBH : 'addctibh' ; ADDCTIBL : 'addctibl' ;

JMP : 'jmp' ;
NOP : 'nop' ;

// Comparator source: (bl | bh | b) (<= | > | =) oN, all glued.
// Written lowercase; caseInsensitive covers 'BL<=O0', 'Bh>o8', etc.
AUX_CMP : 'b' ('l' | 'h')? ('<=' | '>' | '=') 'o' [0-9]+ ;

// A base operand glued to the '+a' relative-addressing suffix. The base may
// be empty, which is how the original assembler reads a bare '+a' (input
// register bit 32, relatively addressed).
REL_OPERAND : NAMEPART* '+' 'a' ;

// A label definition, colon included. ANTLR prefers the longest match, so
// 'loopa:' is one LABEL token instead of LOOPA followed by a stray colon.
LABEL : [a-z_] [a-z0-9_]* ':' ;

// Integers: Python-style literals (hex / octal / binary / decimal), optional
// sign included in the token. ``int(text, 0)`` in the assembler recognises
// the same prefixes.
NUMBER : [-+]? '0' 'x' [0-9a-f]+
       | [-+]? '0' 'o' [0-7]+
       | [-+]? '0' 'b' [01]+
       | [-+]? [0-9]+
       ;

// Anything else word-shaped: source bit names ('o0', 'a15', 'l31', 'l',
// 'h'), label references and, via `identifier`, every keyword token.
NAME : [a-z_] [a-z0-9_]* ;

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

program : line* EOF ;

// One physical line. Content is the bundle/meta statement; labels may
// surround it ('a: set 0 1', 'set 0 1 next_bundle:'), and a label-only line
// is the usual way to mark a target. Two contents on one line ('set 0 1
// set 1 2') are impossible: the original assembler treats such text as one
// malformed element and rejects it.
line : NEWLINE                                  # BlankLine
     | labelDef* lineContent? labelDef* NEWLINE # ContentLine
     ;

labelDef : LABEL ;

lineContent : cfgStmt
            | lutStmt
            | bundle
            ;

// The four 'cfg' keys with their value shapes; allowed spellings ('true'
// vs '1', '8' vs '08') and numeric ranges are checked semantically so the
// historical diagnostics are preserved.
cfgStmt : CFG K_PREFETCH cfgBoolean
        | CFG K_TRAILING_BYTES NUMBER
        | CFG K_EOF_ON (K_UPSTREAM | K_DOWNSTREAM)
        | CFG K_LUT_WIDTH_BITS NUMBER
        | CFG K_LOOP_ENDS_ON (K_EQUAL | K_EQUAL_OR_GREATER)
        ;

cfgBoolean : K_TRUE | K_FALSE | NUMBER ;

// LUT data. Values are separated by spaces or commas; a comma swallows the
// following blank lines and continues the list on the next line. A trailing
// comma is accepted (and ignored), as in the original assembler. Values on
// separate lines without a comma are NOT a continuation: the second line
// then has no content and fails as a stray number.
lutStmt  : LUT lutValue ((COMMA NEWLINE*)? lutValue)* COMMA? ;
lutValue : NUMBER ;

// An instruction bundle: one or more sub-instructions separated by commas.
// A comma must always introduce another sub-instruction, so a dangling
// trailing comma is a syntax error (the original assembler silently dropped
// such an instruction; failing loudly is the chosen replacement).
bundle : subInstr (COMMA NEWLINE* subInstr)* ;

subInstr : setInstr      # SubSet
         | writeInstr    # SubWrite
         | readInstr     # SubRead
         | loopInstr     # SubLoop
         | addInstr      # SubAdd
         | ifInstr       # SubIf
         | ldctdInstr    # SubLdctd
         | ldctiInstr    # SubLdcti
         | addctiInstr   # SubAddcti
         | jmpInstr      # SubJmp
         | nopInstr      # SubNop
         ;

setInstr    : SET outSpec inSpec ;
writeInstr  : WRITE NUMBER ;   // width: semantically restricted to 0/8/16/32
readInstr   : READ NUMBER ;    // width: semantically restricted to 0/8/16/32
loopInstr   : (LOOPA | LOOPB) NUMBER NUMBER labelRef ;  // end_val, ctr_add, tgt
addInstr    : addMnemonic NUMBER ;
ifInstr     : (IF | IFN) condSource labelRef ;
ldctdInstr  : ldctdMnemonic NUMBER ;
ldctiInstr  : ldctiMnemonic ;
addctiInstr : addctiMnemonic ;  // gated per chip, checked semantically
jmpInstr    : JMP labelRef ;    // pseudo-op, assembles to IF h tgt
nopInstr    : NOP ;             // pseudo-op, assembles to ADD hl 0

addMnemonic    : ADDA | ADDAH | ADDAL | ADDB | ADDBH | ADDBL ;
ldctdMnemonic  : LDCTDA | LDCTDAH | LDCTDAL | LDCTDB | LDCTDBH | LDCTDBL ;
ldctiMnemonic  : LDCTIA | LDCTIAH | LDCTIAL | LDCTIB | LDCTIBH | LDCTIBL ;
addctiMnemonic : ADDCTIA | ADDCTIAH | ADDCTIAL | ADDCTIB | ADDCTIBH | ADDCTIBL ;

// Output selection: an output bit number, optionally as a range
// ('0', '0..15', backwards '7..0'). 0..31 bounds checked semantically.
outSpec : NUMBER (RANGE NUMBER)? ;

// Input selection: one source bit or a range of them. Ranges may mix names
// and numbers ('l0..l31', 'o0..15') and run backwards; which combinations
// are meaningful is checked semantically.
inSpec : sourceBit (RANGE sourceBit)? ;

// Condition source for IF/IFN: a single source bit, no range.
condSource : sourceBit ;

sourceBit : AUX_CMP     # CmpSource
          | REL_OPERAND # RelSource
          | NUMBER      # NumericSource
          | identifier  # NamedSource
          ;

// A jump target: the name of a label. Labels may share names with
// mnemonics and cfg keys, so every keyword token is accepted here; numbers
// are deliberately not (numeric jump targets are not part of the language).
labelRef : identifier ;

identifier : NAME | CFG | LUT | SET | WRITE | READ | LOOPA | LOOPB
           | ADDA | ADDAH | ADDAL | ADDB | ADDBH | ADDBL
           | IF | IFN
           | LDCTDA | LDCTDAH | LDCTDAL | LDCTDB | LDCTDBH | LDCTDBL
           | LDCTIA | LDCTIAH | LDCTIAL | LDCTIB | LDCTIBH | LDCTIBL
           | ADDCTIA | ADDCTIAH | ADDCTIAL | ADDCTIB | ADDCTIBH | ADDCTIBL
           | JMP | NOP
           | K_PREFETCH | K_TRAILING_BYTES | K_EOF_ON | K_LUT_WIDTH_BITS
           | K_LOOP_ENDS_ON | K_EQUAL | K_EQUAL_OR_GREATER
           | K_UPSTREAM | K_DOWNSTREAM | K_TRUE | K_FALSE
           ;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fragment NAMEPART : [a-z0-9_] ;
