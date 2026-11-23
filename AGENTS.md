# Repository guide

## Where things live

| Path | Purpose |
| --- | --- |
| `bridge.py` | Bridge launcher and DingTalk message handler |
| `test_bridge.py` | Unit and subprocess regression tests |
| `README.md` | English user guide and safety contract |
| `README.zh-CN.md` | Chinese quick start and troubleshooting |
| `docs/images/` | README flow diagrams (English and Chinese PNG) |
| `LICENSE` | MIT license |
| Test command | `python3 -I -B -m unittest discover -s . -v` |

Keep the bridge DM-only and preserve its allowlist and pending-request safeguards.
Update both READMEs when user-facing behavior or fixed error text changes.
