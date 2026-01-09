# RewindOS — Severance & Cultural Controversy Decay
### “Baby It’s Cold Outside” Case Study

This repository contains the analysis code and outputs supporting a RewindOS case study examining whether the 2018 controversy surrounding the song **“Baby It’s Cold Outside”** still carried measurable cultural risk when it was used in *Severance* (Apple TV+) Season 2, Episode 7 (2025).

The project applies reproducible, data-driven methods to test a simple question:

> **By 2025, was this song still culturally risky to use?**

The results indicate that the controversy peaked briefly in 2018, decayed rapidly, and showed no measurable reactivation across search interest or social engagement when the episode aired.

This repository serves as **proof of method**, not editorial commentary.

---

## Project Scope

This analysis focuses on two independent signals commonly associated with cultural backlash:

1. **Search behavior** (Google Trends)
2. **Social discussion & engagement** (Reddit)

The absence of sustained signal across both channels is treated as a valid analytical outcome.

---

## Repository Contents

### Google Trends Analysis
Scripts that:
- collect controversy-framed search interest from 2018–2025
- smooth and normalize time-series data
- calculate decay slopes and half-life
- extract event windows around the *Severance* air date
- export CSVs and PNGs for reproducibility

### Reddit Social Engagement Analysis
Scripts that:
- query Reddit via public JSON endpoints
- search across broad and narrow query framings
- track post counts, comments, and engagement
- aggregate results weekly
- explicitly detect the absence of backlash

The finding of near-zero discussion is preserved as data, not filtered out.

---

## Key Finding (Summary)

- The controversy surrounding *“Baby It’s Cold Outside”* peaked in late 2018.
- Search interest decayed to baseline by 2020 and remained flat through 2025.
- Reddit discussion linking the song to *Severance* was effectively nonexistent.
- The single post referencing the song framed it as narrative tension, not offense.

In cultural risk terms, the controversy had **expired** well before reuse.

---

## Requirements

### Python
- Python **3.9+** recommended

### Python Libraries

```bash
pip install pandas numpy matplotlib scipy requests pytrends
```

Notes:
- `pytrends` is used for Google Trends access
- Reddit analysis uses public JSON endpoints only
- No API keys or OAuth credentials are required

---

## How to Run

Each script is designed to be run independently.

```bash
python rewindos_google_trends_decay.py
python rewindos_reddit_no_backlash_tracker.py
```

Outputs are written to local CSV and PNG files and include:
- debug logs
- error reports
- raw intermediate data for auditing

Empty or near-empty outputs are valid analytical results and are documented.

---

## Methodological Notes

- “No data” is treated as a finding, not a failure
- Multiple query variants are used to mitigate search limitations
- All time windows and parameters are logged
- Analysis relies only on public data sources

For the generalized framework used here, see the **RewindOS Cultural Safety White Paper** linked from the accompanying blog post.

---

## Relationship to RewindOS

This repository supports the RewindOS blog post:

**“Severance and the Math of Cultural Safety”**

The blog post presents the applied case study.  
The framework itself is documented separately as a generalized white paper.

---

## Disclaimer

This project is independent and does not represent Apple, Apple TV+, the creators of *Severance*, or any affiliated entity.

---

## License

MIT License
