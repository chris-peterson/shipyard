# Execute quietly

<!-- A shipyard template. Copy it into a plugin whose skills narrate their own
     steps (as guides/execute-quietly.md, say), link it from each SKILL.md that
     runs helper scripts, and name that plugin's own scripts and output lines in
     place of the generic ones below. -->

A skill's steps are operating instructions, not a script to read aloud. Run
them, and show the user the result, not the process. Output is for the points
where the user has to act or decide.

When you do speak, write it bottom line up front
([BLUF](https://en.wikipedia.org/wiki/BLUF_(communication))): the result or the
decision you need comes first, and anything supporting it follows, if it is
needed at all. A reader who stops after the first sentence should still know
what happened and what, if anything, they have to do.

## Two leaks to cut

- **The preamble:** "I'll set up the tasks, confirm the repo, and run the
  tests." The user sees each step happen; announcing it first adds nothing.
- **The plumbing:** "the ahead count is 1, the gate is closed, let me read its
  output." A helper's `KEY=value` lines are the input to your next decision,
  not something to relay.

## Fewer steps beats a stronger warning

Narration grows with the number of tool calls the model can see: each separate
step is a place to say "now let me…". A line telling the model not to narrate
has to win that fight on every turn.

The durable fix is structural. Fold deterministic, multi-step work (range math,
lookups whose results feed a fixed decision, tool launches) into one script
call that prints one structured result. Six narrated steps become one launch
and one read. Keep the prose rule for what is left around the steps that need
judgment or the user: drafting text, presenting options, reading feedback.

When a sibling skill turns out to narrate too, that is a missed sweep, not a
failed rule: look for other skills with the same multi-step preamble and fold
them in the same pass. And make the folded script fail loudly; a script that
quietly degrades on a failed read hides the failure the steps used to show.

## Show the finished artifact

Silence covers the intermediates. The thing the user is there to decide on (a
commit message, a description, a drafted issue) has to reach them as text in
your reply or through a tool that shows it. A command's output goes to you, not
the user; the terminal collapses it. So a command run only to present something
presents nothing, and a confirmation prompt about content the user never saw is
the failure to avoid.

## Don't narrate the reasoning behind a decision

The decision is output; its derivation is not. The tell is a sentence that
explains why before it shows what, chaining internal facts toward a conclusion:

> "No config set, the gate is closed, so this is an ordinary commit, but HEAD
> is `main`, so a branch first."

Show the drafted message and the branch options, and nothing else.

## What is output

- A question you need answered.
- A failing check, in full.
- The drafted artifact and its options.
- The final result. Where a step prescribes exact output (`Committed <sha>`),
  emit that and nothing more.
- Feedback the user gave through a side channel (a review tool's comments),
  echoed back before you act on it, since they have no other sign you got it.
