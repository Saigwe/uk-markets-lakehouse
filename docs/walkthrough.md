# 3-minute walkthrough: UK Markets & Macro Lakehouse

A timed script for a Loom recording of about 3 minutes (screen plus camera bubble, 1080p). Say it in your own words; the lines are a guide, not a teleprompter.

**Open these tabs before you press record:** README, ingestion/, dbt/models, terraform/, GitHub Actions (CI + weekly canary).

| Time | On screen | What to say |
|---|---|---|
| 0:00–0:20 | Portfolio card, then the README title | Official statistics get revised after publication, so a dashboard that overwrites can't say what was known when a decision was made. This lakehouse keeps all 69 releases of UK monthly GDP on Iceberg, with time travel. |
| 0:20–0:45 | README intro and the Data section | At a Big Four firm I delivered BI for public-sector and energy clients. This rebuilds that public-finance work on open ONS and Bank of England data. No client data is used. |
| 0:45–1:10 | README architecture: branch → audit → publish | Each release is written to its own Iceberg branch and audited. Only then is it published to main and tagged. |
| 1:10–1:35 | The audit log in Numbers | The audits caught real upstream problems: a release missing total GDP, one with conflicting duplicates, and a listed release with no file. Readers never saw them. |
| 1:35–2:00 | `terraform/` | The AWS deployment is in Terraform: S3, Glue, Athena with a scan cap, and Fargate on a schedule with least-privilege IAM. |
| 2:00–2:30 | The revision analysis | First estimates of monthly GDP growth moved 0.21 points on average, and 10 of 71 months changed direction. All 69 releases load in 14.5 seconds, and a rerun publishes nothing. |
| 2:30–2:45 | `docs/design_doc.md`, the options table | The decision I'd defend in an interview: Measure revisions on growth rates, so re-referencing an index isn't mistaken for a revision. |
| 2:45–3:00 | Back to the README top | For an analytics team, that means 'what did we know on 15 May?' has an answer, and a broken upstream file can't reach a board pack. The repo, numbers and design doc are linked under the video. |

## Recording checklist
- Close email, chat and notifications. Zoom the browser to 125% so code is readable.
- Run `make fixture-all` once before recording, so CI-style output is fresh if you show it.
- Keep to one take per section; Loom lets you trim. Aim for 2:45 to 3:10.
- Show real numbers on screen as you say them; never estimate on camera.
- Say "synthetic" out loud wherever the README labels data as synthetic.

## After recording
1. Copy the Loom share link.
2. In `README.md`, replace the roadmap line with `- [x] [3-minute Loom walkthrough](<your Loom link>)` and add the link under the title.
3. Add the link to this project's card on saigwe.github.io.
