# Lean In Circle Recommendations

A deterministic recommendation API that helps members find relevant, active Circles with room to join. Python 3.10+ and SQLite; no pip packages, API keys, or external services.

## Run locally

Extract this folder, open a terminal inside it, and run:

```bash
python3 app.py
```

On Windows, use `py app.py` if `python3` is unavailable. Open these URLs in a browser:

* http://127.0.0.1:8000/health
* http://127.0.0.1:8000/users/42/recommendations
* http://127.0.0.1:8000/users/7/recommendations?limit=5
* http://127.0.0.1:8000/users/15/recommendations
* http://127.0.0.1:8000/users/23/recommendations

Or use `curl 'http://127.0.0.1:8000/users/23/recommendations?limit=5'`.
Stop with Ctrl+C. The server binds only to localhost. Each startup creates/reseeds `circles.sqlite3` from the supplied JSON; this is a disposable evaluation database. Use `--db another.sqlite3` or `--port 8001` to change these defaults.

### Time reference

The supplied data is a frozen September 2026 snapshot. The default reference date is **2026-09-21 UTC**, matching the snapshot, rather than the evaluator's wall clock. It is returned as `as\_of` in every response. To evaluate freshness at another date:

```bash
python3 app.py --as-of 2026-11-06
```

This changes timestamp freshness, but does not recompute the supplied 30-day aggregates. A live service would refresh those aggregates with the clock. Most candidates eventually expire; the API returns an empty list if none are eligible.

## API

`GET /users/{user\_id}/recommendations?limit=5`

* Positive integer user ID; limit is an integer 1–20, default 5.
* 200: user exists; zero or more recommendations, up to the limit.
* 400: invalid ID, limit, repeated limit, or unknown query parameter.
* 404: unknown user or route.
* GET `/health` returns readiness and the reference date.

Each recommendation has `id`, `name`, `slug`, `topic` (nullable), `format`, `join\_policy`, `score`, and `explanation`. The score is an internal relative ranking value, not a probability. Request-to-join Circles are explicitly described as such.

## Ranking decisions

1. Exclude existing memberships, unlisted Circles, full Circles, and activity older than 90 days (or dated after the reference date). Capacity uses the provided `member\_count`, not the membership export count.
2. Affinity = 0.65 for a primary-topic interest match + 0.25 × fraction of stated interests matched by topic/tags. Tags are deduplicated. With no stated interests, use 0.35 for a primary-topic match to an existing membership instead.
3. Health = 0.6 × exp(-days\_since\_activity / 30) + 0.4 × volume. Volume averages log-saturated feed (cap 20) and chat (cap 100) counts. Final score = 0.75 × affinity + 0.25 × health. Constants are explicit starting heuristics, not learned weights.
4. Sort descending by score, breaking ties by ascending ID. Greedily keep at most one Circle per primary topic. Untopiced Circles use their unique slug. Return fewer results rather than relax eligibility or repeat a topic.
5. Produce explanations from the exact matching signals and freshness window. Cold-start copy never pretends to know the member's interests.

No inference of gender, ethnicity, parenthood, or career goals from names, photos, or bios. No profile-completeness penalty. Circle location is absent, so format is returned for the member to assess; we cannot claim local geographic compatibility.

## Verify

```bash
python3 -m unittest discover -s tests -v
```

On Windows: `py -m unittest discover -s tests -v`.
The suite covers all four planted scenarios, invariants for all 100 users, capacity boundaries, empty results, null topics, future/stale activity, inference, request copy, database integrity/reseeding, and actual HTTP requests/errors.

Expected seeded behavior:

|User|Expected result|
|-|-|
|42|Five active recommendations across different topics; no invented personalization|
|7|Public-speaking and leadership-skills lead the list; #6 and #1 are the top two|
|15|Exactly one of negotiation Circles #10/#11/#12 appears|
|23|Healthy alternative #22 ranks first; full #20 and stale #21 are excluded|

\#1 narrowly outranks the planted #5 on recency and feed activity. Both are healthy leadership matches; the rule picks #1 consistently without a special case for the test records.

## Files

* `app.py`: HTTP routes, validation, CLI, and database startup.
* `recommender.py`: transactional seed loader, eligibility, scoring, diversity, explanations.
* `schema.sql`: normalized SQLite tables, foreign keys, checks, indexes.
* `DESIGN.md`: one-page technical design.
* `tests/test\_recommendations.py`: unit and HTTP integration tests.
* `DATASET.md`, `data/`, `generate.mjs`: original synthetic dataset documentation and files.
* `GITHUB\_STEPS.md`: manual publishing instructions.

## Scope and AI use

This is a local take-home implementation, with a single-process HTTP server and no authentication. Production additions and known limitations are in `DESIGN.md`.

ChatGPT/Codex assisted me with dataset inspection, implementation, tests, and documentation. The recommendation rules are explicit and inspectable; no runtime LLM is used. Before submission I have reviewed the code, run the tests and make sure the outputs are appropriated.

