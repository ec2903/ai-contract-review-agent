# Design notes

## Problem

Each month a team of finance reviewers records every newly signed customer
pricing agreement in a shared workbook. For each contract, a reviewer:

1. finds the matching workbook row,
2. reads the term dates, platform-wide discount and product-specific rates,
3. extracts the year-by-year spend commitment schedule,
4. classifies the commitment and the upfront payment structure,
5. looks up the approved discount band (a 2-D table: term x commitment tier, or term x storage volume),
6. decides whether anything is an outlier,
7. checks termination rights and credits,
8. writes standard-format notes and fills about 25 columns.

At month end a manager merges every reviewer's copy into one file.

None of this needs pricing judgement: it is *reading* followed by *table lookups*.
The hard part is the reading, because contracts state the same commitment in a
dozen different ways.

## Goals

- One prompt per reviewer produces every owned row, fully noted.
- The same contract gets the same determination, whoever runs it.
- Anything uncertain is flagged and left for a person, never guessed.
- A person can see exactly what the machine wrote.
- Contract data stays on the reviewer's machine.

## Key decisions

### 1. The LLM reads; code decides

An earlier version put the entire rulebook in the agent prompt and let the
model apply it. That worked, but range lookups and arithmetic done by a
model are a needless source of variance. Here the model's output is narrowed
to a typed extraction (`schemas/contract_fields.schema.json`) with a quoted
clause behind every key value. Everything downstream is plain Python that can
be unit-tested.

| Concern | Model | Code |
|---|---|---|
| "Is this spend language binding?" | ✅ reads and quotes the clause | |
| "Which tier is $3.0M average annual?" | | ✅ rulebook lookup |
| "Is 17% an outlier?" | | ✅ band + materiality gate |
| "Write the notes" | supplies 1-2 observations | ✅ fixed template |

### 2. The rulebook is data

`rules/rulebook.yaml` holds every band, tier, category and phrase list. A policy
change is a one-line diff anyone on the team can review. The code holds no
numbers, and the prompt holds no pricing logic, so the prompt stays the same
from month to month.

### 3. Extraction is isolated and disposable

`extract.py` is the only module that knows about PDFs. It writes one text file
per contract with `===== Page N of M =====` markers, so a reviewer can open
exactly what the agent read. It also records a per-page character count:
a near-empty page is an image-only (scanned) page, flagged at extraction time
instead of surfacing later as a silently missing term.

### 4. The spreadsheet is someone else's interface

The consuming team owns the workbook layout, so the code adapts to it:

- columns are found by **header name**, never by letter;
- **input** columns (owner, file, agreement ID, customer) and **formula**
  columns are never written, and attempting to write them raises an error;
- each write first confirms the row's file name matches;
- only written cells are filled yellow;
- the master is never saved over. Each reviewer writes `<master> - <initials>.xlsx`;
- an Excel lock file (`~$...`) stops the run before Excel can clobber the changes.

### 5. Audit before save

`audit.py` re-checks every written row. Each check exists because the mistake
is easy to make and hard to spot in a spreadsheet:

- **Term Commitment rule.** For an annual-only deal the term column must be
  blank. Repeating the annual sum there falsely signals a separately
  negotiated term commitment.
- Sum of annual commitments = Year 1-5.
- Category and upfront type are from the rulebook vocabulary.
- Percentages are whole numbers.
- Notes have all three parts: summary, numbered list, outlier conclusion.
- The Outlier column agrees with the conclusion line.
- Formula columns still hold formulas.

If any check fails, the file is not saved.

### 6. Consolidation is code, not a prompt

Merging finished rows is matching, copying and conflict detection, with nothing
to interpret. Asking a model to do it is slower, less predictable, and risks it
"helpfully" re-analysing a row a reviewer already signed off. `consolidate.py`
is deterministic, writes only a new `- Consolidated` copy, takes from each file
only the rows its owner owns, never overwrites a value with a blank, resolves
duplicates first-wins (and reports them), and supports `--dry-run`. The agent
always shows the dry-run plan and waits for confirmation.

## Alternatives considered

| Option | Why not |
|---|---|
| Upload contracts to a chat assistant | Batch and file-size limits, and it produces a summary, not the ~25 populated workbook columns, which is where most of the time goes. |
| Regex / template parser | Contracts have no fixed shape. Commitment wording varies too much to parse reliably. |
| Prompt-only agent (rules in the prompt) | Works, but lookups and arithmetic vary from run to run and can't be unit-tested. This design keeps the model only for reading. |
| Status quo | ~1 hour per contract, inconsistent between reviewers. |

## Known limits and next steps

- Extraction quality depends on the PDF having a text layer. Scanned pages are flagged, not OCR'd.
- The rulebook is maintained by hand and needs a refresh procedure when pricing guidance changes.
- Next: an evaluation set of saved contract texts with expected extractions, to measure the reading step the same way the tests measure the deciding step.
