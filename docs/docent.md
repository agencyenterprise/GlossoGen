# Searching runs with Docent

[Docent](https://transluce.org/docent) is Transluce's tool for reading and
searching agent transcripts. Follow these steps to run Docent on your own
machine, load one glossogen run into it, and ask it a question about the run.
Docent stores agent runs. An agent run holds transcripts, and a transcript is
one agent's messages in order. The glossogen run goes in as one agent run, built from its
[ATIF export](atif-export.md), with one transcript per agent.

| Step | What it needs |
| --- | --- |
| [1. Run Docent locally](#1-run-docent-locally) | Docker, git, and about 1.3 GB of disk for the images |
| [2. Get an API key](#2-get-an-api-key) | a browser |
| [3. Export a run as ATIF](#3-export-a-run-as-atif) | glossogen and a finished run |
| [4. Upload the run](#4-upload-the-run) | uv |
| [5. Search the run](#5-search-the-run) | an OpenAI API key, and about 95,000 `gpt-5` tokens for the run on this page |

Nothing here uses Transluce's hosted Docent. Docent keeps its data in Docker on
your machine. In step 5, Docent sends the run's transcripts to OpenAI.

## 1. Run Docent locally

```bash
git clone https://github.com/TransluceAI/docent.git
cd docent
git checkout 7a477df
cp .env.template .env
```

Open `.env` and set `OPENAI_API_KEY`. Step 5 needs it, and steps 1 to 4 do
not. Then build and start Docent, and create its tables:

```bash
DOCENT_WEB_PORT=3002 DOCENT_PG_PORT=5435 DOCENT_REDIS_PORT=6381 \
  docker compose up -d --build
docker compose exec backend alembic upgrade head
```

Docker Compose starts five containers: the API, a worker, the web UI, Postgres
and Redis. The command puts the web UI, Postgres and Redis on other ports than
Docent's defaults. A glossogen setup already uses the default ports:

| Service | Docent's default port | Port on this page | What uses the default port |
| --- | --- | --- | --- |
| Web UI | 3000 | 3002 | glossogen's web UI. Its [Langfuse stack](observability.md) uses 3001 |
| Postgres | 5432 | 5435 | the local Postgres in [Installation](installation.md). Langfuse's Postgres uses 5433 |
| Redis | 6379 | 6381 | Langfuse's Redis |
| API | 8888 | 8888 | nothing in glossogen |

To stop Docent, run `docker compose down` in the `docent` folder. It keeps
Docent's data. `docker compose down -v` deletes the data as well.

**Build at commit `7a477df`.** Later commits remove `package-lock.json`. The
web UI's Dockerfile runs `npm ci`, which fails without that file. At commit
`731cbd3`, `uv.lock` also pins `tokenizers` 0.13.3. That version has no wheel
for Python 3.12, which the API image uses, so the API build stops at
`can't find Rust compiler`.

**Set the keys in `.env` before you build.** The build copies `.env`, keys
included, into the API and worker images. A key that you add later needs
`docker compose up -d --build` again. Leave the file readable by other users
(mode 644). The containers read it as an unprivileged user, and with mode 600
the API fails to start with
`PermissionError: [Errno 13] Permission denied: '/app/.env'`.

**Create the tables before you sign up.** Until
`docker compose exec backend alembic upgrade head` has run, the signup page
fails with an internal server error.

## 2. Get an API key

Open <http://localhost:3002/signup> and sign up with any email address and
password. The account is a row in Docent's local Postgres, and Docent sends no
email.

Open <http://localhost:3002/settings/api-keys>, click **Create API Key**, give
the key a name, and copy the key. It starts with `dk_`, and the page shows it
only once. Put it in the shell that runs step 4:

```bash
export DOCENT_API_KEY=dk_...
```

## 3. Export a run as ATIF

From your glossogen project, write one ATIF file per agent:

```bash
glossogen export-atif spot_the_intersection \
  --run-dir ./runs/spot_the_intersection/1795535900 \
  --out-dir ./atif/1795535900
```

The run on this page is a game of spot_the_intersection with two agents,
viewer_1 and viewer_2. Each viewer has a private board of objects. The viewers
message each other on a link channel to find the one object on both boards.
The team's score is the number of characters that they send on that channel,
and a lower score is better. After each round, the viewers talk in a discussion
phase, and those messages do not count toward the score.

The web UI writes the same files. Click **Export**, open the **Raw run
folders** tab, and keep **Include ATIF trajectories** ticked. The zip holds the
files under `<scenario>/<run>/atif/`.

![The Export dialog on the Raw run folders tab, with Include ATIF trajectories ticked](../images/docent_atif_export.webp)

## 4. Upload the run

Docent's Python SDK converts one ATIF file into one agent run. The script below
converts each agent's file and puts all the transcripts into a single agent run.
Each transcript belongs to a transcript group, which Docent's web UI shows as
a folder. The script names each group after its agent and model. Save the script as
`upload_to_docent.py`:

```python
"""Upload one glossogen run, exported as ATIF, to a local Docent as one agent run."""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import requests
from docent.data_models import AgentRun, TranscriptGroup
from docent.sdk.integrations import convert_atif_to_agent_run

DOCENT_API = "http://localhost:8888/rest"
DOCENT_WEB = "http://localhost:3002"

atif_dir = Path(sys.argv[1])
trajectories = [json.loads(path.read_text()) for path in sorted(atif_dir.glob("*.json"))]

# One transcript per agent, each in a group named after the agent and its model.
run_id = str(uuid4())
groups = []
transcripts = []
for trajectory in trajectories:
    agent = trajectory["agent"]
    group = TranscriptGroup(
        name=f"{agent['extra']['agent_id']} ({agent['model_name']})",
        agent_run_id=run_id,
    )
    groups.append(group)
    for transcript in convert_atif_to_agent_run(trajectory).transcripts:
        transcripts.append(transcript.model_copy(update={"transcript_group_id": group.id}))

run = AgentRun(
    id=run_id,
    name=trajectories[0]["session_id"],
    transcripts=transcripts,
    transcript_groups=groups,
    metadata={
        "scenario": trajectories[0]["extra"]["scenario_name"],
        "agents": [group.name for group in groups],
    },
)

session = requests.Session()
session.headers["Authorization"] = f"Bearer {os.environ['DOCENT_API_KEY']}"
created = session.post(f"{DOCENT_API}/create", json={"name": "glossogen runs"})
created.raise_for_status()
collection_id = created.json()["collection_id"]
added = session.post(
    f"{DOCENT_API}/{collection_id}/agent_runs",
    json={"agent_runs": [run.model_dump(mode="json")]},
)
added.raise_for_status()
print(f"Uploaded {run.name} as one agent run: {DOCENT_WEB}/dashboard/{collection_id}")
```

Run it on the folder from step 3:

```bash
uv run --no-project --python 3.12 --with docent==0.1.88 \
  python upload_to_docent.py ./atif/1795535900
```

```text
Uploaded spot_the_intersection/1795535900 as one agent run: http://localhost:3002/dashboard/483c76d8-eaa4-486a-99cc-11009df48cb1
```

The link opens a collection, which is Docent's name for a set of agent runs.
Each run of the script creates a new collection named `glossogen runs`.

The script posts the agent run with `requests`, not with the SDK's
`add_agent_runs`. That method sends a gzip-compressed body, which Docent at
`7a477df` rejects: `HTTP 400: There was an error parsing the body`.

On the collection page, click the agent run's row. The left column lists one
transcript group per viewer. The middle column shows the selected transcript,
one message per block. In the screenshot, viewer_1's transcript starts round 1.
In block 3, viewer_1 reads its board. In block 4, it calls `send_message` with
the board written as four-character codes.

![The run in Docent: its metadata, a transcript group per viewer, and blocks 2 to 4 of viewer_1's transcript](../images/docent_agent_run.webp)

## 5. Search the run

On the collection page, type this question into the **Create a rubric** box and
click **Direct search**:

> An agent proposes a new code for the objects on its board, such as a shorter
> way to write a shape, color and cell, for its teammate to use in later rounds.

Docent calls the question a rubric. A judge model reads the whole agent run and
answers whether the run matches the rubric, with an explanation. For this run,
`gpt-5` answered `match` and cited four blocks. A citation such as `T1B50`
means transcript 1, block 50. Transcripts count from 0, in the order of the `agents`
metadata, so transcript 1 belongs to viewer_2.

| Citation | What the block holds |
| --- | --- |
| `T1B50` | viewer_2 proposes a two-character code in the round 2 discussion phase: one base-36 character for the cell, and one hex character for the color and shape |
| `T0B50` | viewer_1 confirms the code for the next round |
| `T0B57` | viewer_1 reads viewer_2's round 3 link message, `4fsau5k1ddtbl7m6cc`, which is nine two-character codes |
| `T0B20` | viewer_1's round 1 discussion message: viewer_2 sends its board, viewer_1 answers with the matching cell in two characters, and each color and shape keeps a one-letter code |

Clicking a citation opens its block in the transcript, next to the result:

![The rubric, the judge's explanation with its four citations, and block 50 of viewer_2's transcript, opened from the T1B50 citation](../images/docent_search_result.webp)

A Direct search also opens a refinement chat. The chat's agent asks you
questions to make the rubric more precise. Docent made two `gpt-5` calls for
this search. The judge call read 90,664 prompt tokens and wrote 2,357
completion tokens, and 1,984 of those were reasoning tokens. The call for the
chat's first question read 1,363 prompt tokens and wrote 369. These counts are
the `usage` fields of OpenAI's two responses. The judge's prompt holds both
transcripts, so a longer run uses more tokens. Docent makes another call for
each answer that you give in the chat.

**Use an OpenAI key for search.** Docent at `7a477df` offers four judges:
OpenAI's `gpt-5` at medium and at low reasoning effort, OpenAI's `gpt-5-mini`,
and Anthropic's `claude-sonnet-4-20250514`. Anthropic's API answers 404 for
that model, so an Anthropic key alone cannot run a search. A new rubric uses
the first judge, `gpt-5` at medium effort.

## Where to go next

- [ATIF export](atif-export.md) describes what a trajectory holds, such as which
  steps are copied context.
- [Exporting runs](exporting-runs.md) covers the raw zip and the CSV tables.
- [Reading runs from code](reading-runs-from-code.md) covers reading a run's
  event log from Python.
