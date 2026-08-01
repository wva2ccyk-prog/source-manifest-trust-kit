# Third-Party Licenses

This public staging package vendors the following third-party browser assets.
These assets are used only by the static local frontend viewer.

Vendored versions are enforced by `tests/test_vendored_frontend_assets.py`, which
parses the banner out of each bundle and holds it to a minimum-version floor. CI's
supply-chain job only scans the Python environment, so that test is the check that
covers these files.

## marked

- File: `frontend/marked.min.js`
- Version noted in bundled file: `18.0.7`
- Project: `https://github.com/markedjs/marked`
- License: MIT
- Bundle source: upstream `lib/marked.umd.js` from the npm release. The 18.x
  release does not ship a pre-minified build; the filename is kept as
  `marked.min.js` so the viewer's script tag is unchanged.

The bundled file preserves the upstream copyright header:

```text
marked v18.0.7 - a markdown parser
Copyright (c) 2018-2026, MarkedJS. (MIT License)
Copyright (c) 2011-2018, Christopher Jeffrey. (MIT License)
```

MIT License text:

```text
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## DOMPurify

- File: `frontend/purify.min.js`
- Version noted in bundled file: `3.4.12`
- Project: `https://github.com/cure53/DOMPurify`
- License noted in bundled file: Apache License 2.0 and Mozilla Public License 2.0

The bundled file preserves the upstream license header:

```text
DOMPurify 3.4.12 | (c) Cure53 and other contributors | Released under the Apache license 2.0 and Mozilla Public License 2.0
```

The previously vendored `3.0.9` predated the 3.x fix for CVE-2024-47875
(nesting-based mXSS), which shipped in `3.1.3`.
