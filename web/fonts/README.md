# Fonts

Self-hosted (the site's CSP allows only same-origin fonts). All are licensed under the SIL Open Font License 1.1 and were downloaded from Google Fonts (Arabic + Latin subsets, woff2):

- **Aref Ruqaa** (Abdullah Aref), 700: wordmark only.
- **Amiri** (Khaled Hosny), 400 and 700: headings and the source book's text.
- **IBM Plex Sans Arabic** (IBM), 400 and 600: interface text.

Each font has an `-arabic` and a `-latin` file, loaded by `unicode-range` from the `@font-face` rules at the top of `web/style.css`. Fonts are served with `Cache-Control: immutable`, so a changed font file needs a new filename. Do not load fonts from Google or any other CDN: the CSP blocks it.

License text: https://openfontlicense.org
