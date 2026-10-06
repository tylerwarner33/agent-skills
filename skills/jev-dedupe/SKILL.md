---
name: jev-dedupe
description: Find duplicate records in a CSV, JSON, or JSONL file with Jev - code finds candidate pairs, Jev decides for each pair if it is the same real-world entity, and the result is a merge plan with confidence values. Claude checks a sample before any merge. Use when the user asks to deduplicate, merge, or clean up records such as companies, contacts, products, or accounts, or to group issues or pull requests by theme.
---

# Jev Dedupe

Messy data often has the same entity two times, ex. "Cedar Grove Office Products" and "Cedar Grove Office". Pair-by-pair comparison with a large model is too slow and too expensive for thousands of records. Jev makes each pair decision in milliseconds, at almost no cost.

The method:

1. Code finds candidate pairs cheaply. Only records that share a word are compared. Very common words are ignored.
2. Jev answers one yes/no question per pair: "Same real-world entity?" Many pairs go in one request, and requests run in parallel.
3. Pairs with a probability at or above the threshold (default 0.95) are joined into merge groups.
4. Claude (the smarter model) checks a sample of the merges and the uncertain pairs.
5. Merges are applied only after the user confirms.

The script never changes the input file. It writes a plan.

Requires the `jev-setup` skill (a key in the environment).

## Procedure

1. Look at the data. Select the fields that identify an entity, ex. `name` and `city` for companies, `name` and `email` for contacts. Do not include fields that change often (ex. `updated_at`).

2. Run:

   ```bash
   python <this-skill-dir>/scripts/find_duplicates.py companies.csv \
     --fields name city --id-field id \
     --out dedupe-plan.json --csv dedupe-pairs.csv
   ```

3. Read `dedupe-plan.json`:
   - `groups`: the records to merge, with the pair probabilities.
   - `uncertain`: pairs from 0.5 up to the threshold. Jev is not sure about them.

4. **Check the plan (necessary).**
   - Select a random sample of at least 10 groups (or all groups, if there are fewer). For each group, decide if the records are really the same entity.
   - Check each uncertain pair the same way.
   - If more than one sampled group is wrong, raise `--threshold` (ex. 0.99) and run again.

5. Optional: for each merge group, write one line that tells why the records are the same (ex. "Same name except the suffix 'Products'; same city").

6. Show the user the number of groups, the sample result, and the uncertain pairs. Ask before you merge.

7. After the user confirms, write the merged data to a **new** file. Keep the original file.

## Settings

| Option | Default | Effect |
| --- | --- | --- |
| `--threshold` | 0.95 | Minimum probability to merge. Use 0.99 when a wrong merge is expensive. |
| `--uncertain-low` | 0.5 | Lower limit of the review list |
| `--min-overlap` | 0.25 | Minimum word overlap for a candidate pair |
| `--max-block` | 200 | Words shared by more records than this are ignored for pairing |
| `--max-pairs` | 5000 | Maximum pairs sent to Jev |
| `--batch` | 25 | Pairs per Jev request |

## Other uses

The same method groups items by theme. Ex. to group issues or pull requests:

1. Export them to JSON with `title` and `body` (or a short summary) fields.
2. Change the question in `judge_batch` to "Do these two items cover the same feature or problem?"
3. Use a lower threshold (ex. 0.8), because a wrong group is cheap to fix.

## Limits

- If two duplicates share no word in the selected fields (ex. "IBM" and "International Business Machines"), the blocking step does not find the pair. Add a field that they share (ex. a website or a phone number).
- Groups are built transitively: if A = B and B = C, then A, B, and C are one group. Check large groups with care.
- Jev judges the selected fields only. It does not see other fields.
