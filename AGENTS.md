# AGENTS.md — OpenCode Agent Instructions

This file provides guidance to AI coding agents (OpenCode, Claude Code, Cursor, etc.) when working with this repository.

## Repository Overview

**Sito** — 山东科技大学（SDUST）的校园办事指南与知识问答系统（"知事通"）。基于云端 LLM + 本地 Qwen3-14B GGUF 的 RAG 系统，提供校园政策查询、审批流程指南、OCR 识别等功能。

- **后端**: Python FastAPI，SQLAlchemy ORM，Redis
- **前端**: React (TypeScript), Vite
- **模型**: Qwen3-14B GGUF (LoRA fine-tuned)，Qwen3-4B/PEFT 管线作为跨平台备选
- **数据**: 爬虫采集自山东科技大学各学院网站

## Agent Skills Integration

This project uses [Agent Skills](https://github.com/addyosmani/agent-skills) (23 skills). Skills are located in:

- **`.github/skills/<name>/SKILL.md`** — 主技能文件（Copilot 用，OpenCode 通过 symlink 访问）
- **`.opencode/skills/<name>/`** — OpenCode symlinks

### Core Rules

- If a task matches a skill, you MUST invoke it
- Skills are in `.github/skills/<skill-name>/SKILL.md` (accessible via symlink in `.opencode/skills/`)
- Never implement directly if a skill applies
- Always follow the skill instructions exactly (do not partially apply them)

### Intent → Skill Mapping

Map user intent to the appropriate skill:

| Intent | Skill |
|--------|-------|
| Feature / new functionality | `spec-driven-development` → `incremental-implementation` + `test-driven-development` |
| Planning / breakdown | `planning-and-task-breakdown` |
| Bug / failure / unexpected behavior | `debugging-and-error-recovery` |
| Code review | `code-review-and-quality` |
| Refactoring / simplification | `code-simplification` |
| API or interface design | `api-and-interface-design` |
| UI work | `frontend-ui-engineering` |
| Security | `security-and-hardening` |
| Performance | `performance-optimization` |

### Lifecycle Mapping (Implicit Commands)

| Phase | Skill |
|-------|-------|
| DEFINE | `spec-driven-development` |
| PLAN | `planning-and-task-breakdown` |
| BUILD | `incremental-implementation` + `test-driven-development` |
| VERIFY | `debugging-and-error-recovery` |
| REVIEW | `code-review-and-quality` |
| SHIP | `shipping-and-launch` |

### Execution Model

For every request:

1. Determine if any skill applies (even 1% chance)
2. Invoke the appropriate skill
3. Follow the skill workflow strictly
4. Only proceed to implementation after required steps (spec, plan, etc.) are complete

### Anti-Rationalization

The following thoughts are incorrect and must be ignored:

- "This is too small for a skill"
- "I can just quickly implement this"
- "I'll gather context first"

**Correct behavior**: Always check for and use skills first.

## Engineering Best Practices

### Testing
- Write tests before code (TDD)
- For bugs: write a failing test first, then fix (Prove-It pattern)
- Test hierarchy: unit > integration > e2e (use the lowest level that captures the behavior)
- Run tests after every change

### Code Quality
- Review across five axes: correctness, readability, architecture, security, performance
- Every PR must pass: lint, type check, tests, build
- No secrets in code or version control

### Implementation
- Build in small, verifiable increments
- Each increment: implement → test → verify → commit
- Never mix formatting changes with behavior changes

### Boundaries
- Always: Run tests before commits, validate user input
- Ask first: Database schema changes, new dependencies
- Never: Commit secrets, remove failing tests, skip verification

## Reference Checklists

For detailed checklists, see:
- `.github/references/testing-patterns.md`
- `.github/references/security-checklist.md`
- `.github/references/performance-checklist.md`
- `.github/references/accessibility-checklist.md`
