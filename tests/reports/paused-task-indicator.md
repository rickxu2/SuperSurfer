# Paused task indicator

Reviewed redacted environment excerpt from the project's Activity diagnostic export
(2026-11-03 22:09 EST): SuperSurfer 0.1.43, macOS 15.8 arm64, Python 3.13.17;
manager connected without error. Private source paths, project/task identifiers,
activity logs, account information and conversations are omitted.

The user's cropped screenshot shows a green task dot after pausing its agent.
A task with saved planning status `preparing` previously returned to that green
state when the turn stopped. A persisted explicit pause was not considered by
status aggregation; while stopping, the still-busy turn also stayed green.

Regression coverage sets the explicit pause through the real Stop action against
an isolated offline CLI fixture, checks red in light/dark themes and after reload,
and checks that resumed active work returns to green. Store regressions verify
planning-state precedence, stop settling, archived sibling ownership, restart
persistence, unrelated scopes and active-agent/run precedence. These tests use no
real provider inference, user jobs or shared service restart.
