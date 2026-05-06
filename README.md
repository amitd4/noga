# noga

Command-line paper search agent for finding academic papers by topic.

The agent searches arXiv, then prints paper titles, authors, publication dates,
abstract summaries, paper links, and PDF links when available. By default it
also downloads the matching PDFs into a local `papers` directory.

## Run

From PowerShell, open the project folder:

```powershell
cd "C:\Users\Danieli Amit\OneDrive\Desktop\projects\noga"
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run the agent:

```bash
python main.py "large language model agents"
```

Limit the number of results:

```bash
python main.py "quantum computing" --max-results 3
```

`--max-results` accepts values from `1` to `25`.

Choose a download directory:

```bash
python main.py "retrieval augmented generation" --download-dir downloads/rag
```

Search without downloading:

```bash
python main.py "graph neural networks" --no-download
```

When you are done, deactivate the virtual environment:

```powershell
deactivate
```
