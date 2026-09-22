# Member-candidate onboarding deck

This directory contains the editable onboarding deck for prospective FØ members.

## Files

- `member-candidate-onboarding.md` is the canonical, reviewable content.
- `member-candidate-onboarding.odp` is the generated OpenDocument presentation and can be edited directly in LibreOffice Impress.
- `member-candidate-onboarding.pdf` is the generated vector PDF for distribution.
- `build_odp.py` generates the ODP and PDF from one scene model and can create a PNG contact sheet for review.
- `assets/f0-wordmark-source.png` preserves the supplied artwork; `f0-wordmark.png` and `f0-mark.png` are exact trimmed derivatives for slide use.
- `assets/Unbounded-VariableFont_wght.ttf` is embedded in the ODP for headings; its SIL Open Font License is stored beside it.

The Markdown is authoritative for maintained releases. Direct ODP edits are useful for one-off presentations, but the next rebuild will replace them.

## Editing the deck

1. Update the relevant public policy page first.
2. Update the matching summary in `member-candidate-onboarding.md`.
3. Keep the `Sources:` line on every slide aligned with the claims on that slide.
4. Rebuild both formats and validate:

   ```sh
   python3 F0RTHSP4CE/onboarding/build_odp.py --check
   ```

5. Create a temporary contact sheet and inspect the layout:

   ```sh
   python3 F0RTHSP4CE/onboarding/build_odp.py \
     --check \
     --preview /tmp/f0-onboarding-contact-sheet.png
   ```

6. Open the ODP in LibreOffice Impress when available and spot-check links, wrapping, and object editability.

The ODP uses only the Python standard library. Vector PDF output uses Pycairo, Pango, PyGObject, and Fontconfig; the optional contact sheet uses Pillow. These dependencies are available in the current development environment.

The PDF is rendered directly from the same parsed slide scene as the ODP. This avoids a LibreOffice runtime dependency and prevents an office converter from changing wrapping or substituting fonts. If somebody edits the ODP manually instead of updating the Markdown, they should export that edited ODP from LibreOffice—the generated PDF only reflects the canonical Markdown pipeline.

Useful options:

```sh
# Skip PDF generation
python3 F0RTHSP4CE/onboarding/build_odp.py --no-pdf

# Choose another PDF destination
python3 F0RTHSP4CE/onboarding/build_odp.py --pdf-output /tmp/onboarding.pdf
```

## Markdown structure

The file begins with simple deck metadata. Slides are separated by a line containing `---`.

Each slide supports:

```md
<!-- layout: single -->
# Slide title

## Section title

- Bullet
- Bullet

Sources: [Source name](https://example.com/source)
```

Supported layouts are `title` for the cover and `list` for every content slide. The builder rejects other layouts, bottom callouts, subtitle/intro copy, missing titles, missing sources, or malformed links.

The placeholders `{git_revision}` and `{generated_date}` are filled during generation. ZIP timestamps and XML metadata are fixed so two builds from the same source, revision, and date are byte-for-byte reproducible.

## Visual system

- Use a black background with only white and acid green (`#00ff00`) text.
- Use Unbounded for display headings and Liberation Sans for body copy.
- Preserve projector-scale typography: 36 pt slide titles, 23–28 pt section headings, and 23–27 pt body copy.
- Use one content column on every slide. Split content into more slides when necessary.
- Use square corners only. Arrows and warning triangles are allowed; rounded shapes are not.
- Do not use decorative vertical rules or bottom motivational callouts.
- Do not add subtitles below slide titles. Split content across more slides instead of reducing body type.
- Render Markdown list items with a right-pointed `>` marker.
- Use `{red}`, `{green}`, or `{white}` before a list-layout section title only for item-marking labels. Use `{private} RED TAPE / RED STICKER | YELLOW STICKER` and `{shared} GREEN STICKER / WHITE TAPE` for stacked labels.

## Policy maintenance rules

- Treat `../Principles.md` as the top-level public baseline.
- Focused pages provide operational detail but should not contradict the principles.
- Mark fees, handles, schedules, and physical locations as current at the source snapshot.
- Do not add access-control details, credentials, private escalation procedures, or private contacts.
- A self-check is guidance, not a new membership requirement.

## Language rules

- Use [ASD-STE100 Simplified Technical English](https://www.asd-ste100.org/) principles for the slide summaries: short sentences, active voice, and one topic per sentence.
- Use direct commands for procedures. Put a necessary condition before the command.
- Use the same word for the same concept. Avoid idioms, vague pronouns, and unnecessary jargon.
- Keep procedural sentences at 20 words or fewer. Keep descriptive sentences at 25 words or fewer.
- Preserve official FØ names and policy labels, even when they are outside the controlled vocabulary.
- Treat this as an STE-style editorial standard. A formal compliance claim requires a separate controlled-vocabulary review.
