# Images

Generated for this project with the owner's Slide Assets MCP (OpenAI image model), then resized and compressed. No text or figures appear in any image.

Files under `/static/img` are served with `Cache-Control: immutable`. Never overwrite an image in place: save the replacement under a NEW filename, point the CSS/HTML at it, and update this list.

## In use

Sizes are chosen for weight: the large photographs are WebP at quality 72 to 80 (re-encoded on 2026-10-07, the "-v2" names), and the hero comes in a 1920px file for ordinary screens and a 2560px file only for sharp (2x) screens through CSS `image-set()`.

- `emblem-112.webp`, `emblem-32.png`, `emblem-180.png` (2026-10-04/05; 112px copy 2026-10-07): eight-petal khatam rosette in gold leaf on bottle green. Logo in the header, sidebar, sign-in window, loaders and empty states (never shown above 56px, hence the 112px file); favicon; touch icon.
- `book-cover.webp` (2026-10-04/05): green leather manuscript binding with a gold-tooled shamsa. Cover on each card in «المصادر».
- `hero-desk-1920.webp`, `hero-desk-2560-v2.webp`, `hero-desk-1280-v2.webp` (2026-10-05): a light wooden desk by a window, a brass balance, two leather books and a reed pen, sage wall with leaf shadows. Background of the public landing page's first screen (1920 on ordinary screens, 2560 on sharp ones, 1280 on tablets and phones).
- `tour-ground-2560.webp`, `tour-ground-1280.webp` (2026-10-07): soft daylight through a sheer curtain, pale sage and ivory, high key. Ground of the landing tour and the closing invitation.
- `overview-analyze-1680-v2.webp` (2026-10-05): an open book, a reed pen and a small brass balance on a desk, sage wall. The «حلّل شبهة» call-to-action band on «نظرة عامة».
- `method-library-1680-v2.webp` (2026-10-05): a library with a carved lattice window, warm light, a book on a low table. The dark "how Manhaj thinks" band on «نظرة عامة».
- `analyze-desk-2560-v2.webp`, `analyze-desk-1280-v2.webp` (2026-10-07): a scholar's desk in bright morning light, an open book, reed pen and inkwell, a brass balance and loose pages at the edges, the middle left empty. The first screen of «حلّل شبهة» (new analysis), under the whole workspace.

Removed on 2026-10-07 because nothing used them: `girih-banner.webp`, `girih-strip.webp`, `analyze-panel-1600.webp`, `empty-history.webp` (and their dead CSS rules).
