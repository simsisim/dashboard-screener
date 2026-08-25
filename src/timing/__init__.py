"""Timing-signal screeners (feedback_4.md) — on-demand, scoped runs.

These answer "should I act right now?" (Buy/Sell state, trailing-stop
level), unlike the candidate screeners in src/leaders/. They are NOT
part of run_screeners.py's daily batch — they run on demand against a
scoped ticker list (see src/on_demand.py and the Timing Signals tab)."""
