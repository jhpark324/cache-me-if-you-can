"""Package the public tour and its referenced assets for GitHub project Pages."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "showcase"
FRONTEND = ROOT / "frontend"
REPOSITORY = "https://github.com/jhpark324/cache-me-if-you-can"
PRESENTATION = "cache-me-if-you-can-graduation-presentation"


class ShowcasePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_header = False
        self.github_links = 0
        self.ids = set()
        self.anchors = set()
        self.assets = set()
        self.linked_anchors = set()
        self.stylesheets = set()
        self.video = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "header":
            self.in_header = True
        if tag == "video":
            if not {"controls", "playsinline", "poster"} <= attrs.keys() or "autoplay" in attrs:
                raise ValueError("Use a poster and user-controlled inline playback for each film.")
            self.video = {"source": bool(attrs.get("src")), "captions": False}
        if self.video is not None:
            if tag == "source" and attrs.get("src"):
                self.video["source"] = True
            if tag == "track" and attrs.get("kind") == "captions" and attrs.get("srclang") == "ko" and attrs.get("src"):
                self.video["captions"] = True
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "link" and attrs.get("rel") == "canonical":
            return
        if tag == "link" and "stylesheet" in attrs.get("rel", "").split() and attrs.get("href"):
            self.stylesheets.add(Path(unquote(urlsplit(attrs["href"]).path)))
        references = [attrs[key] for key in ("href", "src", "poster") if key in attrs]
        if attrs.get("data-motion"):
            references.append(attrs["data-motion"])
        if "srcset" in attrs:
            for candidate in attrs["srcset"].split(","):
                parts = candidate.split()
                if not parts:
                    raise ValueError("Empty responsive image candidate.")
                references.append(parts[0])
        for reference in references:
            url = urlsplit(reference)
            if url.scheme or url.netloc:
                if tag == "a" and self.in_header and reference == attrs.get("href") == REPOSITORY:
                    self.github_links += 1
                    continue
                raise ValueError(f"Unexpected external link or dependency: {reference}")
            if url.path:
                path = Path(unquote(url.path))
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"Asset must be within the published project: {path}")
                self.assets.add(path)
                if url.fragment and path.suffix == ".html":
                    self.linked_anchors.add((path, unquote(url.fragment)))
            elif url.fragment:
                self.anchors.add(unquote(url.fragment))

    def handle_endtag(self, tag):
        if tag == "header":
            self.in_header = False
        if tag == "video" and self.video is not None:
            if not all(self.video.values()):
                raise ValueError("Each film needs a playable source and Korean captions.")
            self.video = None


def assemble(site):
    presentation = site / "presentation"
    presentation.mkdir()
    for extension in (".html", ".pdf"):
        source = ROOT / "docs" / "assets" / (PRESENTATION + extension)
        shutil.copyfile(source, presentation / source.name)

    subprocess.run(
        ["node", "scripts/render-showcase-reference.mjs", SOURCE, site],
        cwd=FRONTEND, check=True,
    )
    for template in SOURCE.glob("*.html"):
        if template.name != "guide-library.html":
            subprocess.run(
                ["node", "scripts/render-showcase.mjs", template, site / template.name],
                cwd=FRONTEND, check=True,
            )
    pages = {}
    referenced = set()
    for html in sorted(site.glob("*.html")):
        page = ShowcasePage()
        page.feed(html.read_text(encoding="utf-8"))
        page.close()
        if page.github_links != int(html.name == "index.html"):
            raise ValueError(f"Check the header GitHub link in {html.name}.")
        if Path("astryx.css") not in page.stylesheets:
            raise ValueError(f"The rendered page must load Astryx styles: {html.name}")
        pages[Path(html.name)] = page
        referenced.update(page.assets)
    for name, page in pages.items():
        for path, anchor in page.linked_anchors | {(name, target) for target in page.anchors}:
            if path not in pages or anchor not in pages[path].ids:
                raise ValueError(f"Missing destination for {name}: {path}#{anchor}")
    stylesheet = Path("astryx.css")
    subprocess.run(
        ["node", "scripts/build-showcase-styles.mjs", site, site / stylesheet],
        cwd=FRONTEND, check=True,
    )
    for relative in referenced - pages.keys() - {stylesheet}:
        if (site / relative).is_file():
            continue  # Already packaged with the presentation or rendered reference documents.
        asset = SOURCE / relative
        if not asset.resolve().is_relative_to(SOURCE) or not asset.is_file() or not asset.stat().st_size:
            raise ValueError(f"Missing or invalid showcase asset: {relative}")
        if relative.suffix == ".vtt" and not asset.read_text(encoding="utf-8").startswith("WEBVTT"):
            raise ValueError(f"Invalid caption file: {relative}")
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, target)
    subprocess.run(
        ["node", "scripts/check-showcase-media.mjs", site], cwd=FRONTEND, check=True,
    )
    return sum(item.is_file() for item in site.rglob("*"))


def build(destination):
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Choose a new destination directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temporary:
        site = Path(temporary) / "site"
        site.mkdir()
        count = assemble(site)
        site.rename(destination)
    print(f"Packaged {count} files for GitHub Pages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new directory for the static site")
    build(parser.parse_args().destination)
