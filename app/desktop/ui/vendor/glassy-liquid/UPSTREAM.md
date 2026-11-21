# glassy-liquid 0.1.0

- Source: https://github.com/9und30/glassy-liquid/tree/f9f701d5de0a10dfaefbba6d6af6f977850d9957
- Release artifact: https://registry.npmjs.org/glassy-liquid/-/glassy-liquid-0.1.0.tgz
- Release artifact integrity: `sha512-kWhyBztp9cVcn/WtVBW/qVlazTXg3pLXD4Afyr/3nxvzLMCxTpw3QCL6gWe3cwSQoh3k4c8/7jRYszRs6vmdAQ==`
- License: MIT, see `LICENSE`.
- Scope: the unmodified ESM output for `components/selector.js` and its 15 static imports.
  No React, network loader, install scripts or other standalone controls are bundled.
- Fixed inline styles emitted by this subset: `sha256-6VS2QfOPrpRdEwAwqTPTpCS6cIeP1wVt07HiahIL35c=` (tab item) and
  `sha256-JXec0A+0wHX/xDF5APd7LGwKMkhf4rj5P+XDeDrPuXg=` (engine).
  The desktop restricts these by hash instead of allowing arbitrary inline styles.
