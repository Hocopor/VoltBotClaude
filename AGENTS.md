# AGENTS

## Live Plan Rule

Always keep a live task plan during the work.

Required behavior:
- At the start of each action, update the plan and mark what is starting, what is done, what is not done, and what is in progress.
- At the end of each completed action, immediately update the plan and record the result.
- If a new task, risk, blocker, or required check appears during the work, add it to the live plan right away.
- If the user explicitly says `otmenyaem` or `ubiraem iz plana`, remove that item from the plan or mark it as canceled. Simply switching attention to another topic is not a cancelation.
- Do not continue substantial work without an up-to-date live plan.
- The plan must always reflect the real current state of the task: `done`, `not done`, `in progress`.
