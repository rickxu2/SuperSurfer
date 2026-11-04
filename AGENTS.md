# Contributing

For repository changes, read [.agents/README.md](.agents/README.md) and follow
[the fix, local build and PR workflow](.agents/contributing.md).

# Local app updates

For this development workspace, the user requested on November 3, 2026 that
agents handle needed local SuperSurfer updates as part of their workflow, rather
than handing back restart commands. This authorizes replacing the local desktop
build and restarting its matching workspace service after validation. Carry this
preference through subsequent app-development tasks without asking again.
Follow the local-update procedure in [.agents/contributing.md](.agents/contributing.md).
Preserve unsaved work and other active tasks; this does not authorize unrelated
merges, remote-host upgrades, research launches or publishing a release.

# Release work

Every SuperSurfer release must include a review and revision of the manager,
research lead, experiment worker, host-onboarding and results skills in `agent_skills/`. Delegate this
bounded review to a subagent when available.

Compare each skill with the actual role tools, context, ownership rules,
permissions and user workflows in that release. Update the capability guidance
and both version markers after the review; do not merely bump the markers.
Confirm that preparation, explicit queue requests and autonomous suggestions
remain distinct, and describe any native-owner capability limitations honestly.

Run `python3 scripts/check-agent-skills.py` and the applicable tests before
packaging. The build blocks missing or stale skills and bundles them into the
workspace service. Keep README, CONTRACT, TODO and VALIDATION consistent with
the resulting behavior and checks.
