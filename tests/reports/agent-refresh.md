# Agent chat refresh diagnostics

Reviewed excerpt of the workspace diagnostic export; unrelated project activity,
command logs, paths, identifiers and chat contents have been omitted.

- App: SuperSurfer 0.1.43, macOS 15.8 arm64, Python 3.13.17.
- Software workflow; this task's checks and preview blocks have no commands.
- No research runs or background rules were active in the exported state.

## Reproduction and diagnosis

Focus the agent composer, select draft text, then scroll partway through a long
conversation. Wait through chat updates and the five-second workspace refresh.
In the workflow view, history moved; in advanced Surfboard, composer focus was
lost. Both paths appended the same existing chat DOM node to its current parent.
Avoiding those redundant moves preserves the focused descendant and scroll state.

## Verification

The browser regression covers overview sidebar, workflow, advanced Surfboard,
chat tile and detached window using temporary projects and simulated messages.
It checks focus, selection direction, typing, unsent draft and reading position.
No live provider credentials, user messages or source excerpts are included here.

## November 2 follow-up: Questions for you

The question renderer replaced its complete form list when request metadata
changed or another card appeared. On the branch with the earlier composer fix,
a browser regression reproduced replacement of the active answer textarea.
Reconcile each card by scoped request identity and question schema, updating
state-only UI in place. The extended regression verifies native input identity,
focus/selection, draft text and both question-container and textarea scroll.
The existing cancellation, expiration and secret-draft checks also pass.
