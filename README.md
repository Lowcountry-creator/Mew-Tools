# Mew-Tools

![tests](https://github.com/Lowcountry-creator/Mew-Tools/actions/workflows/tests.yml/badge.svg)

Engineering calculation utilities. Python 3.9+, standard library only unless a
tool's own README says otherwise.

## Layout

| Path | Purpose |
|---|---|
| `tools/` | One subfolder per tool. Each holds its script, a README, and tests. |
| `tools/hec14_outlet_protection/` | Culvert outlet protection per HEC-14 Ch. 10, with HY-8 import. |

## Conventions

- PEP8, inline comments explaining the engineering, not the syntax.
- Every equation cites its source (manual, chapter, equation number).
- US customary units unless a tool states otherwise.
- Run tests from the repo root: `python -m pytest`.

## License

MIT. See `LICENSE`.
