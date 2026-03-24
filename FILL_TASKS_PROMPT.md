# Prompt: populate tasks.json

Use this prompt with Claude to generate your personalised burn-task list.
Open Claude Code (or claude.ai) in any working directory and paste the following,
filling in the bracketed sections:

---

I want to populate a token-burn task list for my Claude Pro subscription tracker.
The file format is tasks.json and each task has these fields:

```json
{
  "id": "unique-slug",
  "name": "Short human-readable name",
  "description": "One-line description of what this does",
  "working_dir": "~/projects/your-project-name",
  "prompt": "The full prompt to give Claude Code for this task",
  "estimated_tokens": 15000,
  "tags": ["refactor", "docs", "review", "research"],
  "enabled": true
}
```

Here are my active coding projects:
[LIST YOUR PROJECTS HERE — e.g. "my-api: REST API for X", "my-cli: command-line tool for Y"]

Here are areas I'd like to improve or explore:
[LIST TOPICS — e.g. "add tests to my projects", "write better README files", "research X technology", "refactor old code"]

Constraints:
- Each task prompt should be self-contained (Claude should be able to run it cold with no extra context)
- estimated_tokens should be realistic: a simple refactor ~10K, a full code review ~25K, deep research ~30K
- Prefer tasks that produce durable value (docs, tests, refactors) over one-offs
- Include at least 8 tasks across different tags so there's always something useful to queue

Please generate a complete tasks.json `"tasks"` array I can paste into my file.
Aim for tasks ranked by value/token-cost ratio (highest value per token first).

---

Once you have the output, paste the `"tasks"` array into tasks.json and set
`"enabled": true` on any tasks you want active.
