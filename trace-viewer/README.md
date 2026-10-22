# Trace Explorer

Local, browser-only visualizer for `debugmas` trace logs. It is intentionally dependency-free:
open [index.html](index.html) in a Chromium-based browser, choose a folder, and the app recursively
discovers every file named `trace.jsonl` inside it.

Nothing is uploaded. Run names, solvers, task outcomes, counts, events, and token totals are all
parsed from the selected trace files; the viewer does not assume a particular result directory,
task set, or number of runs.

The selected run gets a method-aware display:

- `workflow`: linear proposal / verification / retry timeline;
- `single_agent`: decision and tool-call timeline;
- `mas_sequential`: researcher, fixer, and checker swimlanes.

Task outcomes and candidate attempts have separate filters. The attempt filter keeps the events
that led to accepted or rejected submissions, so an investigator can isolate a retry cycle.

Large prompts and test payloads are hidden behind expandable controls and truncated in the view so
that opening a trace remains responsive.
