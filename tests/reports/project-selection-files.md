# Project selection unexpectedly expands Files

Reviewed redacted excerpt of the project's Activity diagnostic export, generated
2026-11-03 19:29 EST. Only environment facts relevant to this UI bug are retained:
SuperSurfer 0.1.43, macOS 15.8 arm64, Python 3.13.17; manager connected without error.
Project/task identifiers, source paths, activity, command logs and conversations
are omitted. This report contains no credentials or user file content.

Reproduction in an isolated workspace:

1. Use an editor page on the first project, with no saved Files preference.
2. Select another project and then the first project in the left sidebar.
3. Files appears expanded because its HTML starts `open`, although project
   selection never explicitly requests expansion.
4. Close Files and reload: its previous open/collapsed choice was not persisted.

The added browser regression failed before the fix at “Files starts collapsed
until explicitly opened.” After the fix it covers returning to the first project,
explicit opening, preserving open and collapsed choices on reload, and existing
section sizing in browser and desktop layouts. Native preference tests exercise
the same choice through the desktop sanitizer.
