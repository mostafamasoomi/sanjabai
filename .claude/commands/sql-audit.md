---
description: EXPLAIN every raw-SQL literal in backend/*.py against the live Postgres schema (pre-deploy gate)
---

Run the reverse ORM↔DB schema audit and report the result:

```bash
python3 /root/sanjabai/scripts/sql_schema_audit.py
```

Why this exists: the pytest suite mocks `async_session`, so no raw SQL is
ever executed by tests — a misspelled column, a bad `GROUP BY`, or an illegal
`HAVING` ships green and only 500s in production. Session 11 found four such
live 500s this way (`charge_amount` vs `charged_amount`, `HAVING` on an
ungrouped outer query). EXPLAIN plans each statement without executing it, so
the audit is read-only; every statement additionally runs inside
`BEGIN`/`ROLLBACK`.

Run this before every backend deploy. Exit 0 = all statements plan cleanly;
exit 1 = at least one failed (the script prints `FAIL <file:line>` with the
Postgres error). The f-strings it lists under "manual review" build their
column list from a server-side whitelist and cannot be EXPLAINed blind —
check those by hand when you touch them.
