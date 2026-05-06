import argparse
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


@dataclass
class Paper:
    title: str
    authors: List[str]
    summary: str
    published: str
    link: str
    pdf_link: Optional[str]


class PaperSearchAgent:
    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search(self, topic: str) -> List[Paper]:
        if not topic.strip():
            raise ValueError("Please provide a non-empty topic.")

        params = {
            "search_query": f"all:{topic}",
            "start": 0,
            "max_results": self.max_results,
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
    agent = PaperSearchAgent(max_results=args.max_results)

    try:
        papers = agent.search(args.topic)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            print("arXiv is rate-limiting requests right now. Please wait a minute and try again.")
            return
        print(f"Search failed with HTTP {error.code}: {error.reason}")
        return
    except urllib.error.URLError as error:
        print(f"Search failed because the network request could not complete: {error.reason}")
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


if __name__ == "__main__":
    main()
