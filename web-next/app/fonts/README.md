# Local cockpit fonts

Inter (variable 100–900) and JetBrains Mono (variable 100–800) are bundled to make
Next builds independent of Google Fonts availability. Existing CSS variables,
normal style and swap display are retained. Both files include extended Latin,
including Polish characters. No build-time font downloads or new npm package
are required.

`sources.json` records immutable upstream google/fonts commits, URLs and SHA256.
Each font is distributed with its SIL Open Font License 1.1 alongside
it. Update the font, receipt and license together from the official upstream.
The original TTFs are stored in lossless WOFF containers using existing fontTools;
glyph coverage and variable axes are retained. The smaller immutable inputs
replace the TTFs rather than retaining duplicate assets.
