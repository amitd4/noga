import argparse
import math
import re
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
REQUEST_HEADERS = {"User-Agent": "noga-paper-search-agent/0.1"}
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "using",
    "with",
}


@dataclass
class Paper:
    title: str
    authors: List[str]
    summary: str
    published: str
    link: str
    pdf_link: Optional[str]
    relevance_note: Optional[str] = None


class PaperSearchAgent:
    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search(self, topic: str, max_results: Optional[int] = None) -> List[Paper]:
        if not topic.strip():
            raise ValueError("Please provide a non-empty topic.")

        params = {
            "search_query": f"all:{topic}",
            "start": 0,
            "max_results": max_results or self.max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"

        with self._open_url(url, timeout=20) as response:
            data = response.read()

        return self._parse_arxiv_response(data)

    def download_papers(self, papers: List[Paper], download_dir: Path) -> Tuple[List[Path], List[str]]:
        download_dir.mkdir(parents=True, exist_ok=True)
        saved_files = []
        failed_downloads = []

        for index, paper in enumerate(papers, start=1):
            if not paper.pdf_link:
                continue

            filename = self._paper_filename(index, paper)
            destination = download_dir / filename

            try:
                with self._open_url(paper.pdf_link, timeout=60) as response:
                    destination.write_bytes(response.read())
                saved_files.append(destination)
            except urllib.error.HTTPError as error:
                failed_downloads.append(f"{paper.title} (HTTP {error.code})")
            except urllib.error.URLError as error:
                failed_downloads.append(f"{paper.title} ({error.reason})")
            except OSError as error:
                failed_downloads.append(f"{paper.title} ({error})")

        return saved_files, failed_downloads

    def _open_url(self, url: str, timeout: int):
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        delays = [0, 5, 10]

        for attempt, delay in enumerate(delays, start=1):
            if delay:
                time.sleep(delay)

            try:
                return urllib.request.urlopen(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                if error.code == 429 and attempt < len(delays):
                    continue
                raise

    def _parse_arxiv_response(self, data: bytes) -> List[Paper]:
        root = ET.fromstring(data)
        papers = []

        for entry in root.findall("atom:entry", ATOM_NAMESPACE):
            title = self._entry_text(entry, "atom:title")
            summary = self._entry_text(entry, "atom:summary")
            published = self._entry_text(entry, "atom:published")[:10]
            authors = [
                author.findtext("atom:name", default="", namespaces=ATOM_NAMESPACE)
                for author in entry.findall("atom:author", ATOM_NAMESPACE)
            ]

            link = ""
            pdf_link = None
            for link_element in entry.findall("atom:link", ATOM_NAMESPACE):
                href = link_element.attrib.get("href", "")
                title_attr = link_element.attrib.get("title", "")
                rel = link_element.attrib.get("rel", "")

                if rel == "alternate":
                    link = href
                if title_attr == "pdf":
                    pdf_link = href

            papers.append(
                Paper(
                    title=self._clean_text(title),
                    authors=[author for author in authors if author],
                    summary=self._clean_text(summary),
                    published=published,
                    link=link,
                    pdf_link=pdf_link,
                )
            )

        return papers

    def _entry_text(self, entry: ET.Element, tag: str) -> str:
        return entry.findtext(tag, default="", namespaces=ATOM_NAMESPACE)

    def _clean_text(self, value: str) -> str:
        return " ".join(value.split())

    def _paper_filename(self, index: int, paper: Paper) -> str:
        title = re.sub(r"[^A-Za-z0-9._ -]+", "", paper.title)
        title = re.sub(r"\s+", "_", title).strip("._-")
        title = title[:80] or "paper"
        return f"{index:02d}_{title}.pdf"


class HybridSearchRanker:
    def __init__(self):
        self.bm25_cls = self._load_bm25()

    def _recency_bonus(self, published: str) -> float:
        match = re.match(r"(\d{4})", published)
        if not match:
            return 0.0

        year = int(match.group(1))
        if year < 2020:
            return 0.0

        return min(2.0, math.log1p(year - 2019))

    def rank(self, topic: str, papers: List[Paper], limit: int) -> List[Paper]:
        if not papers:
            return []

        documents = [self._paper_text(paper) for paper in papers]
        tokenized_documents = [self._tokens(document) for document in documents]
        topic_tokens = self._tokens(topic)

        bm25_scores = self.bm25_cls(tokenized_documents).get_scores(topic_tokens)
        tfidf_scores = self._tfidf_scores(topic, documents)
        recency_scores = [self._recency_bonus(paper.published) for paper in papers]

        bm25_scores = self._normalize(list(bm25_scores))
        tfidf_scores = self._normalize(tfidf_scores)
        recency_scores = self._normalize(recency_scores)

        scored_papers = []
        for index, paper in enumerate(papers):
            score = (
                bm25_scores[index] * 0.45
                + tfidf_scores[index] * 0.45
                + recency_scores[index] * 0.10
            )
            paper.relevance_note = (
                f"hybrid score {score:.2f} "
                f"(bm25 {bm25_scores[index]:.2f}, tf-idf {tfidf_scores[index]:.2f}, "
                f"recency {recency_scores[index]:.2f})"
            )
            scored_papers.append((score, paper))

        scored_papers.sort(key=lambda item: item[0], reverse=True)
        return [paper for _, paper in scored_papers[:limit]]

    def _paper_text(self, paper: Paper) -> str:
        return f"{paper.title}. {paper.summary}"

    def _tokens(self, text: str) -> List[str]:
        words = re.findall(r"[A-Za-z0-9]+", text.lower())
        return [word for word in words if len(word) > 2 and word not in STOP_WORDS]

    def _tfidf_scores(self, topic: str, documents: List[str]) -> List[float]:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError as error:
            raise RuntimeError(
                "Hybrid ranking dependencies are missing. Run: pip install -r requirements.txt"
            ) from error

        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            max_features=5000,
        )
        try:
            matrix = vectorizer.fit_transform([topic] + documents)
        except ValueError:
            return [0.0 for _ in documents]

        similarities = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
        return [float(score) for score in similarities]

    def _normalize(self, scores: List[float]) -> List[float]:
        if not scores:
            return []

        low = min(scores)
        high = max(scores)
        if high == low:
            return [0.0 for _ in scores]

        return [(score - low) / (high - low) for score in scores]

    def _load_bm25(self):
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as error:
            raise RuntimeError(
                "Hybrid ranking dependencies are missing. Run: pip install -r requirements.txt"
            ) from error

        return BM25Okapi


def format_paper(index: int, paper: Paper) -> str:
    authors = ", ".join(paper.authors[:4])
    if len(paper.authors) > 4:
        authors += ", et al."

    summary = textwrap.fill(paper.summary, width=88)
    lines = [
        f"{index}. {paper.title}",
        f"   Authors: {authors or 'Unknown'}",
        f"   Published: {paper.published or 'Unknown'}",
        f"   Link: {paper.link or 'Unavailable'}",
    ]

    if paper.pdf_link:
        lines.append(f"   PDF: {paper.pdf_link}")

    if paper.relevance_note:
        lines.append(f"   Relevance note: {paper.relevance_note}")

    lines.extend(["   Summary:", textwrap.indent(summary, "     ")])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search academic papers on arXiv for a given topic."
    )
    parser.add_argument("topic", help="Topic to search for, wrapped in quotes if needed.")
    parser.add_argument(
        "-n",
        "--max-results",
        type=positive_int,
        default=5,
        help="Number of papers to return. Default: 5.",
    )
    parser.add_argument(
        "-d",
        "--download-dir",
        default="papers",
        help="Directory where downloaded PDFs are saved. Default: papers.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Only print search results without downloading PDFs.",
    )
    parser.add_argument(
        "--no-rank",
        action="store_true",
        help="Use arXiv's original ordering without local reranking.",
    )
    parser.add_argument(
        "--hybrid-rank",
        action="store_true",
        help="Use BM25 plus TF-IDF similarity. This is the default ranking mode.",
    )
    parser.add_argument(
        "--candidate-pool",
        type=positive_int,
        default=10,
        help="Number of arXiv candidates to fetch before local reranking. Default: 10.",
    )
    return parser


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a whole number")

    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")

    if number > 25:
        raise argparse.ArgumentTypeError("must be 25 or less to avoid overloading arXiv")

    return number


def main() -> None:
    args = build_parser().parse_args()
    if args.no_rank and args.hybrid_rank:
        print("Choose either --no-rank or --hybrid-rank, not both.")
        return

    agent = PaperSearchAgent(max_results=args.max_results)

    try:
        papers = search_and_rank(agent, args)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            print("arXiv is rate-limiting requests right now. Please wait a minute and try again.")
            return
        print(f"Search failed with HTTP {error.code}: {error.reason}")
        return
    except urllib.error.URLError as error:
        print(f"Search failed because the network request could not complete: {error.reason}")
        return
    except RuntimeError as error:
        print(error)
        return

    if not papers:
        print(f"No papers found for: {args.topic}")
        return

    print(f"Top {len(papers)} papers for: {args.topic}\n")
    for index, paper in enumerate(papers, start=1):
        print(format_paper(index, paper))
        print()

    if args.no_download:
        return

    download_dir = Path(args.download_dir)
    saved_files, failed_downloads = agent.download_papers(papers, download_dir)

    if not saved_files:
        print("No PDFs were available to download.")
    else:
        print(f"Downloaded {len(saved_files)} PDF(s) to: {download_dir.resolve()}")
        for saved_file in saved_files:
            print(f"- {saved_file.name}")

    if failed_downloads:
        print("\nSome PDFs could not be downloaded:")
        for failed_download in failed_downloads:
            print(f"- {failed_download}")


def search_and_rank(agent: PaperSearchAgent, args: argparse.Namespace) -> List[Paper]:
    if args.no_rank:
        return agent.search(args.topic)

    candidate_count = max(args.candidate_pool, args.max_results)
    candidates = agent.search(args.topic, max_results=candidate_count)

    return HybridSearchRanker().rank(args.topic, candidates, args.max_results)


if __name__ == "__main__":
    main()
