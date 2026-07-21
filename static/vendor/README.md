# Vendored browser libraries

These files are stored locally so Interpres-Atom's user interface works
without internet access.

- `marked.min.js`: marked 15.0.12, downloaded from
  `https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js`.
  License: MIT (`LICENSE.marked.md`).
- `purify.min.js`: DOMPurify 3.2.6, downloaded from
  `https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist/purify.min.js`.
  License: Apache-2.0 or MPL-2.0 (`LICENSE.DOMPurify.txt`).

Do not replace these files with runtime CDN references. Version updates must
be downloaded and reviewed as part of an Interpres-Atom release.
