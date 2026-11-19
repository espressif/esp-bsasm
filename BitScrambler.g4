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
// rel_addr conflicts, per-chip instruction support - is checked by the
// assembler (src/bsasm/sema.py); see tools/bsasm/README.md for the full
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
// * Numbers keep an optional sign in the token so that '-0x10' reaches the
//   assembler as one word and is rejected with the historical "not an
//   integer" diagnostic, instead of being silently split into '-' and
//   '0x10'.

grammar BitScrambler;

// ---------------------------------------------------------------------------
// Lexer
// ---------------------------------------------------------------------------

// A comment runs from '#' to the end of the line. The line terminator
// itself is not part of the comment and still terminates the statement.
COMMENT : '#' ~[\r\n]* -> skip ;

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
CFG : C F G ;
LUT : L U T ;

K_PREFETCH        : P R E F E T C H ;
K_TRAILING_BYTES  : T R A I L I N G '_' B Y T E S ;
K_EOF_ON          : E O F '_' O N ;
K_LUT_WIDTH_BITS  : L U T '_' W I D T H '_' B I T S ;
K_LOOP_ENDS_ON    : L O O P '_' E N D S '_' O N ;
K_EQUAL           : E Q U A L ;
K_EQUAL_OR_GREATER: E Q U A L '_' O R '_' G R E A T E R ;
K_UPSTREAM        : U P S T R E A M ;
K_DOWNSTREAM      : D O W N S T R E A M ;
K_TRUE            : T R U E ;
K_FALSE           : F A L S E ;

// Instruction mnemonics.
SET   : S E T ;
WRITE : W R I T E ;
READ  : R E A D ;

LOOPA : L O O P A ;
LOOPB : L O O P B ;

ADDA : A D D A ;  ADDAH : A D D A H ;  ADDAL : A D D A L ;
ADDB : A D D B ;  ADDBH : A D D B H ;  ADDBL : A D D B L ;

IF  : I F ;
IFN : I F N ;

LDCTDA : L D C T D A ; LDCTDAH : L D C T D A H ; LDCTDAL : L D C T D A L ;
LDCTDB : L D C T D B ; LDCTDBH : L D C T D B H ; LDCTDBL : L D C T D B L ;

LDCTIA : L D C T I A ; LDCTIAH : L D C T I A H ; LDCTIAL : L D C T I A L ;
LDCTIB : L D C T I B ; LDCTIBH : L D C T I B H ; LDCTIBL : L D C T I B L ;

ADDCTIA : A D D C T I A ; ADDCTIAH : A D D C T I A H ; ADDCTIAL : A D D C T I A L ;
ADDCTIB : A D D C T I B ; ADDCTIBH : A D D C T I B H ; ADDCTIBL : A D D C T I B L ;

JMP : J M P ;
NOP : N O P ;

// Comparator source: (bl | bh | b) (<= | > | =) oN, all glued.
// Covers e.g. 'bl<=o0', 'bh>o8', 'b=o16' and their upper-case spellings.
AUX_CMP : [bB] ([lL] | [hH])? ('<=' | '>' | '=') [oO] [0-9]+ ;

// A base operand glued to the '+a' relative-addressing suffix. The base may
// be empty, which is how the original assembler reads a bare '+a' (input
// register bit 32, relatively addressed).
REL_OPERAND : NAMEPART* '+' [aA] ;

// A label definition, colon included. ANTLR prefers the longest match, so
// 'loopa:' is one LABEL token instead of LOOPA followed by a stray colon.
LABEL : [A-Za-z_] [A-Za-z0-9_]* ':' ;

// Integers: hex, binary or decimal, with an optional sign. The sign is part
// of the token; whether a spelling is acceptable ('-0x10' is not, '-10' is)
// is a semantic decision and keeps its historical diagnostic.
NUMBER : [-+]? '0' [xX] [0-9a-fA-F]+
       | [-+]? '0' [bB] [01]+
       | [-+]? [0-9]+
       ;

// Anything else word-shaped: source bit names ('o0', 'a15', 'l31', 'l',
// 'h'), label references and, via `identifier`, every keyword token.
NAME : [A-Za-z_] [A-Za-z0-9_]* ;

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
// Case-insensitive keyword fragments
// ---------------------------------------------------------------------------

fragment A:[aA]; fragment B:[bB]; fragment C:[cC]; fragment D:[dD];
fragment E:[eE]; fragment F:[fF]; fragment G:[gG]; fragment H:[hH];
fragment I:[iI]; fragment J:[jJ]; fragment K:[kK]; fragment L:[lL];
fragment M:[mM]; fragment N:[nN]; fragment O:[oO]; fragment P:[pP];
fragment Q:[qQ]; fragment R:[rR]; fragment S:[sS]; fragment T:[tT];
fragment U:[uU]; fragment V:[vV]; fragment W:[wW]; fragment X:[xX];
fragment Y:[yY]; fragment Z:[zZ];

fragment NAMEPART : [A-Za-z0-9_] ;
