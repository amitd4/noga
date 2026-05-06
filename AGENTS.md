# AGENTS.md

Guidance for coding agents working in this repository.

## Project overview

This is a small Python command-line tool for searching arXiv papers by topic,
reranking results locally, and optionally downloading PDFs.

The default ranking mode is hybrid ranking:

- BM25 keyword scoring
- TF-IDF cosine similarity
- a small recency bonus

No external API keys are required.

## Safe working rules

- Keep changes focused on the user's request.
- Do not delete user-created files unless the user explicitly asks.
- Do not commit downloaded papers, virtual environments, caches, or local test files.
- Treat `papers/`, `downloads/`, `.venv/`, and `__pycache__/` as local artifacts.
- Avoid adding network services, background processes, databases, or new frameworks unless
  the user asks for them.
- Prefer simple Python standard-library code unless a dependency clearly improves the tool.
- If adding a dependency, add it to `requirements.txt` and explain why it is needed.

## Development workflow

Use the project virtual environment when running commands:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run a quick search without downloads:

```powershell
python main.py "AI agents tool use" --max-results 2 --no-download
```

Run with raw arXiv ordering:

```powershell
python main.py "AI agents tool use" --no-rank --max-results 2 --no-download
```

## Testing expectations

Before finishing code changes, run at least:

```powershell
python main.py --help
python main.py "AI agents tool use" --max-results 2 --no-download
```

If ranking code changes, also test:

```powershell
python main.py "AI agents tool use" --candidate-pool 10 --max-results 2 --no-download
```

Avoid full PDF download tests unless the change affects downloading. arXiv can rate-limit
requests, so prefer `--no-download` for routine verification.

## Git guidance

- Commit only intentional project files.
- Leave unrelated or untracked user files alone.
- Use concise commit messages, for example:

```text
Improve paper ranking
Update README usage
Handle download errors
```
