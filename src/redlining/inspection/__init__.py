"""redlining.inspection: one run, from the first prompt to the written report.

    session       walks the checklist, or hands the walk to the orchestrator
    orchestrator  an LLM front end over the same step_item
    report        the append-only log, the flag queue and the report

session and orchestrator import each other, and that is why they share a
package. orchestrator needs MAX_REASKS and step_item, so its import of
session is a plain one; session defers its two (CLARIFY, and the three LLM
classes in run_agent) into the function bodies that use them. Breaking the
cycle properly means moving step_item somewhere both can reach, which is a
change to the loop rather than to the layout, so it is not done here.

All three are re-exported at their old top-level paths.
"""
