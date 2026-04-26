---
species: any
topic: task-conventions
source_name: PawPal task-naming heuristics (internal guidance)
source_url: internal://pawpal
---

## Naming maps to category

When a user enters a task title, the words usually map to a known care category:
- "walk", "stroll", "fetch", "run", "play outside" → exercise
- "feed", "feeding", "meal", "breakfast", "dinner", "wet food" → feeding
- "brush", "brushing", "groom", "grooming", "bath", "nail", "teeth" → grooming
- "med", "medication", "pill", "insulin", "heartworm", "flea", "tick" → medications
- "vet", "checkup", "exam", "vaccine" → vet-visit
- "play", "training", "puzzle", "enrichment", "toy" → enrichment

## When the title is ambiguous

If the title doesn't fit any of these categories, lean on the closest match by intent rather than refusing to suggest. The user can override the suggestion before saving.

## Frequency defaults by category

- exercise → daily for healthy adults
- feeding → daily (multiple times for puppies/kittens)
- grooming → weekly to monthly depending on coat
- medications → as prescribed; default daily for unknown meds
- vet-visit → once
- enrichment → daily

## Priority defaults by category

- medications, feeding, exercise → high (welfare-critical)
- grooming, enrichment → medium
- one-off observations → low or medium
