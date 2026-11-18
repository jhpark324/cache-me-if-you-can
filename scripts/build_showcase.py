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


class ShowcasePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_header = False
        self.github_links = 0
        self.ids = set()
        self.anchors = set()
        self.assets = set()
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
    index = site / "index.html"
    subprocess.run(
        ["node", "scripts/render-showcase.mjs", SOURCE / "index.html", index],
        cwd=FRONTEND, check=True,
    )
    stylesheet = Path("astryx.css")
    subprocess.run(
        ["node", "scripts/build-showcase-styles.mjs", index, site / stylesheet],
        cwd=FRONTEND, check=True,
    )
    page = ShowcasePage()
    page.feed(index.read_text(encoding="utf-8"))
    page.close()
    if page.github_links != 1 or page.anchors - page.ids:
        raise ValueError(f"Check the header GitHub link and fragment targets: {sorted(page.anchors - page.ids)}")
    if stylesheet not in page.stylesheets:
        raise ValueError("The rendered showcase must load its Astryx stylesheet.")
    generated = {stylesheet, Path(index.name)}
    for relative in page.assets - generated:
        asset = SOURCE / relative
        if not asset.resolve().is_relative_to(SOURCE) or not asset.is_file() or not asset.stat().st_size:
            raise ValueError(f"Missing or invalid showcase asset: {relative}")
        if relative.suffix == ".vtt" and not asset.read_text(encoding="utf-8").startswith("WEBVTT"):
            raise ValueError(f"Invalid caption file: {relative}")
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, target)
    return len(page.assets | generated)


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
