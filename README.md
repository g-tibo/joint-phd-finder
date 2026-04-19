# NTU Joint PhD Finder

A faculty directory and AI-match tool for NTU's
[Joint PhD Programmes](https://www.ntu.edu.sg/graduate-college/admissions/programme/Joint-PhD-Programmes).
It covers NTU and its partner universities in one browsable list, and helps
faculty and prospective / current PhD students identify potential supervisors
and co-supervisors.

Adapted from [SG Collab Finder](https://github.com/g-tibo/sg-collab-finder),
which itself was inspired by
[plen-collab-finder](https://plen-collab-finder.vercel.app/).

## v1 coverage

- **NTU** — all faculty imported from SG Collab Finder's NTU subset (SBS, SPMS,
  CCEB, ASE, CEE, EEE, MAE, MSE, CCDS, LKCMedicine).
- **Sorbonne University** — biology only — Joint PhD **Degree**
- **Technical University of Munich** — biology only — Joint PhD **Supervision**
- **University of Turin** — biology only — Joint PhD **Supervision**

Partner-university biology is the v1 template; additional disciplines (chemistry,
engineering, medicine) and additional partner universities will follow.

## Repository layout

```
joint-phd-finder/
├── web/               Next.js 15 + TypeScript + Tailwind app
│   ├── app/           Browse (/), AI Match (/match), About (/about)
│   ├── app/api/match  Claude ranking endpoint with 3 branching prompts
│   ├── public/        faculty.json lives here
│   └── package.json
└── scraper/           Python scrapers → scraper/out/*.json → web/public/faculty.json
    ├── scrapers/      One extractor per partner institution + the imported NTU data
    ├── merge.py       Combines per-institution JSON, tags partner_university/type
    └── requirements.txt
```

## Quickstart

Node 20+.

```bash
cd web
npm install
npm run dev           # open http://localhost:3000
```

A seed `web/public/faculty.json` is committed.

## AI Match branches

The AI Match page routes to different prompts depending on who's searching:

1. **Faculty at NTU** — rank partner-university faculty as Joint PhD
   co-supervisors. Optional: select your own NTU profile so your research
   areas are factored in.
2. **Faculty at a partner university** — rank NTU faculty as Joint PhD
   partners.
3. **Prospective PhD student** — rank *supervisor teams* (one NTU faculty
   paired with one-or-more partner faculty) whose expertise complements the
   student's project.
4. **Current PhD student** — pick your current NTU supervisor; rank partner
   faculty whose work complements your supervisor's line of research.

For branches 1, 2, and 4 you can optionally narrow to one or more partner
universities. For branch 3 the picker controls which partner side is searched
when building teams.

## Refresh the faculty data

```bash
cd scraper
pip install -r requirements.txt
python -m scrapers.sorbonne_bio       # -> scraper/out/sorbonne_bio.json
python -m scrapers.tum_bio            # -> scraper/out/tum_bio.json
python -m scrapers.turin_bio          # -> scraper/out/turin_bio.json
python merge.py                       # -> web/public/faculty.json
```

NTU data is carried over from SG Collab Finder's existing scrapers
(`scrapers.ntu_sbs`, `ntu_spms`, etc. — run those if you want a fresh NTU
snapshot; otherwise `merge.py` preserves the committed NTU records).

## Deploy to Vercel

1. Push the repo to GitHub.
2. Import on vercel.com → set **Root Directory** to `web`.
3. Optional: add `ANTHROPIC_API_KEY` as an environment variable so visitors
   don't need their own key.
4. Deploy.

## Data and ethics

All profile data is scraped from public institutional web pages. The About
page exposes a contact email so researchers can request correction or removal.
No user accounts, analytics, or tracking; AI match queries are not retained
by this site.

## License

MIT.
