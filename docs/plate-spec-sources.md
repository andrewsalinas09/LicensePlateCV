# Brazilian Plate Specification — Sources and Numbers

Research pass 2026-07-22. Primary sources:
- CONTRAN Resolução 780/2019, Anexo I (official PDF, gov.br) — geometry figures I/II
- CONTRAN Resolução 969/2022 Anexos (in-force consolidation; geometry unchanged)
- CONTRAN Resolução 231/2007 (old pre-2018 plates), Res. 372/2011 (moto update)

## Mercosur car plate (implemented in `plate_spec.MERCOSUR_BR_CAR`)

| Item | Value | Source |
|---|---|---|
| Plate size | 400×130 ±2 mm (moto 200×170) | Res.780 Anexo I item 2.1 Tabela I |
| Substrate | aluminum 1 ±0.2 mm; white retroreflective film; chars = non-retro hot-stamp film | items 2.2.1–2.2.3 |
| Font | FE-Engschrift | item 2.4.1.1 |
| Char height | 65 mm (moto 53) | item 2.4.1.2 |
| Char layout | 7 equidistant cells, 46 mm pitch (322 mm field), block ends ~38 mm from right edge | Figure II dim chain |
| Band | 30 mm tall × 390 mm, Pantone 286 (#0032A0) | item 2.3.2 Tabela II |
| Band contents | MERCOSUL emblem 32×22 mm; "BRASIL" white Gill Sans Bold Cond; flag 28×20 mm | items 3.1–3.2, Fig. II |
| Border | NONE — film runs to plate edge (dark frame in figures is the separate plastic moldura) | items 5.5–5.6 |
| Corner radius | undocumented; ~10 mm from drawings (PROVISIONAL) | visual estimate |
| Relief height | "alto relevo", numeric value NOT publicly specified anywhere; using 1.2 mm industry-typical (PROVISIONAL) | — |
| Char colors | private black; commercial Pantone 186C (#C8102E); official 286C; diplomatic 130C; special 341C | item 4.4 Tabelas |
| Retroreflectivity | white ≥50 cd/lux/m² @0.2°/−4° (ASTM E-810); chromaticity boxes in Tabelas IV–V | Tabelas IV–V |
| Other elements (not yet rendered) | QR 16–22 mm top-left; "BR" Gill Sans 20 mm bottom-left; micro-lettering in strokes; film watermark every 72 mm; 2 fixing slots 18 mm | items 3.3–3.5, Fig. V |

Layout caveat: the Figure II dimension chain sums to 386 mm vs 400 mm plate width
(drawing datum appears to be the frame inner edge). Renderer places the 322 mm
character field ending 38 mm from the right edge → first cell center at 63 mm.
To be validated pixel-level against real HR crops (design-01 validation gate).

Brazilian usage deviation from German FE practice: glyphs are CENTERED PER
46 mm CELL (equidistant), not typeset with font advances. Real plates are
stamped by many accredited estampadores with minor die variations → per-plate
glyph variation is a noise/nuisance term, not a spec item.

## Old Brazilian plate (pre-2018, `plate_spec.BRAZIL_OLD_CAR`)

400×130 mm; char height 63 mm, stroke 10 mm; font "Mandatory" (Charles
Wright style); raised painted border; private = gray bg / black chars,
commercial = red bg / white chars. (Res. 231/2007; category colors partly from
secondary sources.) Slot positions still PROVISIONAL.

## Fonts (in `data/fonts/`, gitignored — re-download via URLs)

`GL-Nummernschild-Eng.ttf` (44,480 B) — FE-Engschrift digitization by
Gutenberg Labo (2009-11), traced from official German FZV Anlage 4 drawings.
Embedded license: free for any use incl. commercial, "AS IS" — safe.
Source: raw.githubusercontent.com/drorgl/license-plate-generator/master/fonts/
Also fetched: Mittelschrift TTF/OTF variants + legacy FE-FONT.TTF (unclear
provenance — do not use).

FE-Schrift design history: Karlgeorg Hoefer for the German Bundesanstalt für
Straßenwesen (1978-80); no official digital font was ever published; multiple
free digitizations circulate without enforcement.
