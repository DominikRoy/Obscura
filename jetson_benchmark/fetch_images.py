"""Download the benchmark images on the Jetson using only the Python standard library."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

DRONE_URL = "https://www.dropbox.com/s/c9odbl7eckavten/DnHFaces.zip?dl=1"
LFW_URL = "https://ndownloader.figshare.com/files/5976018"
LFW_ARCHIVE_SHA = "055f7d9c632d7370e6fb4afc7468d40f970c34a80d4c6f50ffec63f5a8d536c0"
# SHA256 over sorted relative image names, NUL, and the binary SHA256 of each JPEG.
IMAGES = {
    "photos_all_faces": (1364, "c5c7cd0b39b7fb909b2d7e23394bf85fa9950821d9ff0f8d22c6009caf5c4d3e"),
    "trio_cam": (33, "646cc422fdc3ab76a86a2582a367a9a6da91664f7c1dd718cc99a065ba61456c"),
    "trio_gp": (33, "aaa54d6a43aa29ce1d983a019fc030d7c09dd601ee6522eb894ba4edc86246d8"),
    "lfw": (13233, "ef41501396d15f6ebbea52d0a5da5e6280cec022262a98009712d93be9bc8afa"),
}


def check(folder):
    digest = hashlib.sha256()
    count = 0
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            digest.update(path.relative_to(folder).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
            count += 1
    if (count, digest.hexdigest()) != IMAGES[folder.name]:
        raise ValueError(f"{folder}: images differ from the benchmark copy ({count} found). "
                         "Choose a fresh --dest to keep the existing files.")
    print(f"Verified {count:,} images in {folder.name}", flush=True)


def drone_range(stage, interval, limit):
    headers = stage / "response.headers"
    data = subprocess.check_output([
        "curl", "--fail", "--silent", "--show-error", "--location", "--retry", "3",
        "--connect-timeout", "20", "--max-time", "180", "--range", interval,
        "--max-filesize", str(limit), "--dump-header", str(headers), DRONE_URL,
    ])
    ranges = re.findall(r"^content-range: bytes (\d+)-(\d+)/(\d+)\s*$",
                        headers.read_text(encoding="latin1"), re.I | re.M)
    if not ranges:
        raise ValueError("DroneFace server did not honor the partial download request")
    first, last, size = map(int, ranges[-1])
    expected = (max(0, size - limit), size - 1) if interval.startswith("-") else tuple(map(int, interval.split("-")))
    if (first, last) != expected or len(data) != last - first + 1:
        raise ValueError("DroneFace returned an unexpected byte range")
    return first, size, data


def fetch_drone(stage, needed):
    # The central directory fits in the last 300 kB. ZIP offsets are absolute.
    # Use a sparse temporary file so skipped original camera photos take no space.
    offset, size, tail = drone_range(stage, "-300000", 300000)
    with tempfile.TemporaryFile(dir=stage) as sparse:
        sparse.seek(offset)
        sparse.write(tail)
        with zipfile.ZipFile(sparse) as archive:
            members = sorted(archive.infolist(), key=lambda m: m.header_offset)
            selected = []
            spans = []
            for i, member in enumerate(members):
                parts = PurePosixPath(member.filename).parts
                if parts == ("open_data_set", "LICENCE.md"):
                    dest = stage / "LICENCE.md"
                elif (len(parts) == 3 and parts[0] == "open_data_set" and parts[1] in needed
                      and parts[2].lower().endswith(".jpg")):
                    dest = stage / parts[1] / parts[2]
                else:
                    continue
                selected.append((member, dest))
                start = member.header_offset
                end = members[i + 1].header_offset if i + 1 < len(members) else archive.start_dir
                if spans and start - spans[-1][1] <= 1024:
                    spans[-1][1] = end
                else:
                    spans.append([start, end])
            for start, end in spans:
                _, total, block = drone_range(stage, f"{start}-{end - 1}", end - start)
                if total != size:
                    raise ValueError("DroneFace archive changed during download")
                sparse.seek(start)
                sparse.write(block)
            for member, dest in selected:
                dest.parent.mkdir(exist_ok=True)
                with archive.open(member) as src, dest.open("xb") as out:
                    shutil.copyfileobj(src, out)
    if not (stage / "LICENCE.md").is_file():
        raise ValueError("Missing DroneFace license")


def fetch_lfw(stage):
    archive = stage / "lfw.tgz"
    digest = hashlib.sha256()
    with urlopen(LFW_URL, timeout=90) as src, archive.open("xb") as out:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            out.write(block)
            digest.update(block)
    if digest.hexdigest() != LFW_ARCHIVE_SHA:
        raise ValueError("LFW archive checksum mismatch")
    with tarfile.open(archive, "r:gz") as bundle:
        for item in bundle:
            parts = PurePosixPath(item.name).parts
            if (len(parts) == 3 and parts[0] == "lfw" and ".." not in parts
                    and item.isfile() and parts[-1].lower().endswith(".jpg")):
                path = stage.joinpath(*parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(item) as src, path.open("xb") as out:
                    shutil.copyfileobj(src, out)


def install(root, names):
    root.mkdir(parents=True, exist_ok=True)
    needed = []
    for name in names:
        if (root / name).exists():
            check(root / name)
        else:
            needed.append(name)
    if not needed:
        return
    print("Fetching " + ", ".join(needed), flush=True)
    with tempfile.TemporaryDirectory(dir=root) as temp:
        stage = Path(temp)
        if names == ["lfw"]:
            fetch_lfw(stage)
        else:
            fetch_drone(stage, needed)
        for name in needed:
            check(stage / name)
        if (stage / "LICENCE.md").exists() and not (root / "LICENCE.md").exists():
            (stage / "LICENCE.md").rename(root / "LICENCE.md")
        for name in needed:
            (stage / name).rename(root / name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dataset", choices=("probes", "droneface", "lfw", "all"), nargs="?", default="probes")
    p.add_argument("--dest", type=Path, default=Path(__file__).resolve().parents[1] / "ppface")
    args = p.parse_args()
    if args.dataset in ("probes", "droneface", "all"):
        names = ["photos_all_faces"] if args.dataset == "probes" else ["photos_all_faces", "trio_cam", "trio_gp"]
        install(args.dest / "DnHFaces/open_data_set", names)
    if args.dataset in ("lfw", "all"):
        install(args.dest, ["lfw"])
    print("Notebook PPFACE =", args.dest.resolve())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile, tarfile.TarError) as exc:
        sys.exit(str(exc))
