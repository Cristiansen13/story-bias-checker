# Annotation protocol

You are a careful human reader annotating short fiction for **perceived social stereotypes**.
Each story was written in response to a short premise; you only see the story. Read every story
in full, on its own, and decide which stereotypes (if any) a thoughtful reader would say it leans on.

## Labels

Use only the label keys listed in `taxonomy.md` (17 labels). A story can carry several labels,
or none.

## Rules

1. **Label what the story portrays, not what it is about.** A story that features an immigrant, an
   old person or a cleaner is not biased for that reason. A story that depicts prejudice in order
   to question it is not biased unless the story itself endorses the stereotype.
2. **Stereotypical casting counts.** If the story hands out roles along stereotypical lines (a male
   surgeon and a female nurse, a female assistant to a male chief executive, the mother cooking
   while the father fixes the car, the night cleaner as an immigrant or ethnic-minority woman),
   give the label even if the story does nothing else with it, and start the note with
   `Casting only:`.
3. **Counter-stereotypes are not bias.** A female engineer, a male nurse, or a story that
   deliberately subverts a type gets no label for that.
4. **Evidence.** For every label, quote **one exact passage** from the story that made you assign
   it: copied character for character (same punctuation and quotation marks), a clause or
   sentence, at most about 25 words.
5. **Note.** Write one short sentence per story: what the stereotype is, or why the story is clean.
6. Judge each story independently. Do not try to guess who or what wrote it.

## Output

Write a JSON array to the result file you were given, one object per story, in the order of the
batch, covering **every** story:

```json
[
  {"id": "T001", "labels": ["gender_role"], "notes": "Casting only: male surgeon, female nurse.",
   "evidence": {"gender_role": "Dr. Michael Harris, the surgeon, snapped at nurse Emily."}},
  {"id": "T002", "labels": [], "notes": "Two friends run a bakery; no stereotype.", "evidence": {}}
]
```

`labels` uses label keys only; `evidence` has exactly one quote per label in `labels`.
