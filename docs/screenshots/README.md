# Screenshots

Referenced directly by the root `README.md`:

| Filename | What it shows |
|---|---|
| `setu.gif` | The dashboard in motion — hero + live negotiation feed |
| `negotiation.png` | "Try it yourself" — product/budget picker + the risk-of-conflict chart converging |
| `negotiation-1.png` | The negotiation replayed as a two-party chat, ending in a closed deal |
| `results.png` | The Test Results tab — real scenario-harness numbers |
| `certificate.png` | The result card's "Download verification certificate" button, after a real completed payment |

PNG/GIF, ~1200–1600px wide is plenty — GitHub scales them down in the README
anyway. Keep GIFs trimmed and compressed (see the tip below) — a full-length
screen recording gets large fast.

```bash
# Shrink a raw screen recording into a lightweight, README-sized GIF
ffmpeg -i raw-recording.mov -vf "fps=12,scale=900:-1" -loop 0 setu.gif
```
