#!/usr/bin/env python3
"""Publish the newest stable Fulldex iPhone/iPad release as a LiveContainer source."""

import argparse
import hashlib
import io
import json
import os
import plistlib
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen

UPSTREAM = "mamesj/pokemon-fulldex"
PROJECT = f"https://github.com/{UPSTREAM}"
RELEASES_API = f"https://api.github.com/repos/{UPSTREAM}/releases"
BUNDLE_ID = "io.github.mamesj.pokemonds"
IPA_NAME = "pokemon-ds-wide-ios.ipa"
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source.json"
ICON = ROOT / "icon.png"
STATUS = ROOT / "status.json"


def get(url, headers=None):
    request = Request(url, headers={"User-Agent": "fulldex-livecontainer-source", **(headers or {})})
    with urlopen(request, timeout=90) as response:
        return response.read(), response.headers


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def latest_ios_release():
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    candidates = []
    for page in range(1, 1001):
        body, response_headers = get(f"{RELEASES_API}?per_page=100&page={page}", headers)
        for release in json.loads(body):
            if release["draft"] or release["prerelease"] or not release["published_at"]:
                continue
            assets = [asset for asset in release["assets"] if asset["state"] == "uploaded"]
            ipa = next((asset for asset in assets if asset["name"] == IPA_NAME), None)
            if ipa is None:
                ios_assets = [
                    asset for asset in assets
                    if re.search(r"(?i)(?:^|[-_.])(?:ios|iphone|ipad)(?:[-_.]|$)", asset["name"])
                    and asset["name"].lower().endswith(".ipa")
                ]
                if len(ios_assets) > 1:
                    raise ValueError(f"Ambiguous iOS assets in {release['tag_name']}")
                if ios_assets:
                    ipa = ios_assets[0]
            if ipa:
                candidates.append((release, ipa))
        if 'rel="next"' not in response_headers.get("Link", ""):
            break
    else:
        raise ValueError("Release listing did not finish")

    if not candidates:
        raise ValueError("No stable official release with an iOS IPA was found")
    return max(candidates, key=lambda pair: (pair[0]["published_at"], pair[0]["id"]))


def asset_url(release, asset):
    tag = quote(release["tag_name"], safe="")
    name = quote(asset["name"], safe="")
    expected = f"{PROJECT}/releases/download/{tag}/{name}"
    if asset["browser_download_url"] != expected:
        raise ValueError("Unexpected upstream asset URL")
    return expected


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_ipa(release, asset, url):
    data, _ = get(url)
    digest = sha256(data)
    expected = asset.get("digest")
    checksum = next(
        (a for a in release["assets"] if a["name"] == "SHA256SUMS.txt" and a["state"] == "uploaded"),
        None,
    )
    if checksum:
        sums, _ = get(asset_url(release, checksum))
        pattern = rf"(?mi)^([a-f0-9]{{64}})[ \t]+\*?{re.escape(asset['name'])}[ \t]*\r?$"
        match = re.search(pattern, sums.decode("utf-8"))
        if match:
            published = f"sha256:{match[1].lower()}"
            if expected and expected != published:
                raise ValueError("GitHub's digest and upstream SHA256SUMS.txt disagree")
            expected = published
    if len(data) != asset["size"] or expected != f"sha256:{digest}":
        raise ValueError("IPA size or official SHA-256 verification failed")

    with zipfile.ZipFile(io.BytesIO(data)) as ipa:
        if bad_file := ipa.testzip():
            raise ValueError(f"IPA ZIP integrity check failed: {bad_file}")
        plists = [
            path for path in ipa.namelist() if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", path)
        ]
        if len(plists) != 1:
            raise ValueError("Expected a single main iOS app bundle")
        info = plistlib.loads(ipa.read(plists[0]))
        app_dir = str(PurePosixPath(plists[0]).parent)
        if info["CFBundleIdentifier"] != BUNDLE_ID:
            raise ValueError("Bundle ID changed; refusing to replace the existing app listing")
        if info["CFBundleSupportedPlatforms"] != ["iPhoneOS"]:
            raise ValueError("IPA is not built for an iPhone or iPad")
        executable = info["CFBundleExecutable"]
        if "/" in executable or not ipa.getinfo(f"{app_dir}/{executable}").file_size:
            raise ValueError("IPA is missing its app executable")

        # Use the packaged primary iPhone icon at the largest available scale.
        icon_files = info["CFBundleIcons"]["CFBundlePrimaryIcon"]["CFBundleIconFiles"]
        for suffix in ("@3x.png", "@2x.png", ".png", ""):
            paths = [f"{app_dir}/{name.removesuffix('.png')}{suffix}" for name in icon_files]
            if icon_path := next((path for path in paths if path in ipa.namelist()), None):
                icon = ipa.read(icon_path)
                if icon.startswith(b"\x89PNG\r\n\x1a\n"):
                    return info, icon, digest
        raise ValueError("No packaged iPhone primary icon PNG was found")


def generate_source(release, asset, url, info, icon_url):
    version = info["CFBundleShortVersionString"]
    build = info["CFBundleVersion"]
    date = release["published_at"]
    notes = f"Official Fulldex release: {release['tag_name']}."
    name = info.get("CFBundleDisplayName") or info["CFBundleName"]
    return {
        "name": f"{name} for LiveContainer",
        "identifier": "io.github.spcrts1-arch.pokemon-fulldex-source",
        "website": PROJECT,
        "description": "Community catalog linking to official Pokémon Fulldex iOS releases.",
        "iconURL": icon_url,
        "apps": [{
            "name": name,
            "bundleIdentifier": info["CFBundleIdentifier"],
            "developerName": UPSTREAM.split("/")[0],
            "localizedDescription": "Play your own compatible Nintendo DS and Game Boy Advance ROMs.",
            "iconURL": icon_url,
            "version": version,
            "versionDate": date,
            "versionDescription": notes,
            "downloadURL": url,
            "size": asset["size"],
            "versions": [{
                "version": version,
                "buildVersion": build,
                "buildNumber": build,
                "date": date,
                "localizedDescription": notes,
                "downloadURL": url,
                "size": asset["size"],
                "minOSVersion": info["MinimumOSVersion"],
            }],
        }],
        "news": [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icon-url", required=True)
    parser.add_argument("--verify", action="store_true", help="Reverify even if the asset is unchanged")
    args = parser.parse_args()

    release, asset = latest_ios_release()
    url = asset_url(release, asset)
    now = datetime.now(timezone.utc)
    try:
        previous = json.loads(STATUS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        previous = {}

    if (
        not args.verify
        and previous.get("downloadURL") == url
        and previous.get("assetUpdatedAt") == asset["updated_at"]
        and previous.get("publishedAt") == release["published_at"]
        and previous.get("iconURL") == args.icon_url
        and previous.get("lastVerifiedAt", "")[:7] == now.strftime("%Y-%m")
        and asset.get("digest") == f"sha256:{previous.get('sha256')}"
        and SOURCE.is_file()
        and sha256(SOURCE.read_bytes()) == previous.get("sourceSHA256")
        and ICON.is_file()
        and sha256(ICON.read_bytes()) == previous.get("iconSHA256")
    ):
        print(f"Already verified: {release['tag_name']}")
        return

    info, icon, digest = verify_ipa(release, asset, url)
    source = json_text(generate_source(release, asset, url, info, args.icon_url)).encode("utf-8")
    status = {
        "release": release["tag_name"],
        "publishedAt": release["published_at"],
        "assetUpdatedAt": asset["updated_at"],
        "downloadURL": url,
        "sha256": digest,
        "iconURL": args.icon_url,
        "iconSHA256": sha256(icon),
        "sourceSHA256": sha256(source),
        "lastVerifiedAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    ICON.write_bytes(icon)
    SOURCE.write_bytes(source)
    STATUS.write_text(json_text(status), encoding="utf-8")
    print(f"Verified {release['tag_name']}: {info['CFBundleShortVersionString']} "
          f"(build {info['CFBundleVersion']}), {len(icon)} byte icon, SHA-256 {digest}")


if __name__ == "__main__":
    main()
