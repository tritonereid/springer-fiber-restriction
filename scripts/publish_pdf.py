#!/usr/bin/env python3
"""Publish a GitHub reading copy and an immutable, versioned manuscript PDF."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


class APIError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f"GitHub HTTP {status}: {message}")


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, data=None, binary=False):
        host = "https://uploads.github.com" if binary else "https://api.github.com"
        body = data if binary else json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(
            host + path, data=body, method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/pdf" if binary else "application/json",
                "User-Agent": "manuscript-publication",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read()).get("message", "request failed")
            except ValueError:
                message = "request failed"
            raise APIError(exc.code, message.replace(self.token, "[redacted]")) from None


def publish(api, repository, source_sha, branch, version, pdf):
    base = "/repos/" + repository
    filename = "A_Restriction_Theorem_for_Springer_Fibers.pdf"
    tag = "v" + version
    readme = Path("README.md").read_text(encoding="utf-8")
    title = readme.splitlines()[0].removeprefix("# ")
    pages = re.search(r"(?m)^\*\*Comments:\*\* ([0-9]+) pages?\s*$", readme)
    if not pages:
        raise ValueError("README.md must state the manuscript page count in its Comments field")
    page_count = int(pages[1])
    source = api.request("GET", base + "/git/commits/" + source_sha)
    tree = api.request("GET", base + "/git/trees/" + source["tree"]["sha"])
    existing_blob = next((item["sha"] for item in tree["tree"] if item["path"] == filename), None)
    expected_blob = hashlib.sha1(b"blob " + str(len(pdf)).encode() + b"\0" + pdf).hexdigest()
    published_sha = source_sha
    if existing_blob != expected_blob:
        blob = api.request("POST", base + "/git/blobs", {
            "content": base64.b64encode(pdf).decode(), "encoding": "base64",
        })
        pdf_tree = api.request("POST", base + "/git/trees", {
            "base_tree": source["tree"]["sha"],
            "tree": [{"path": filename, "mode": "100644", "type": "blob", "sha": blob["sha"]}],
        })
        bot = {
            "name": "github-actions[bot]",
            "email": "41898282+github-actions[bot]@users.noreply.github.com",
            "date": source["committer"]["date"],
        }
        commit = api.request("POST", base + "/git/commits", {
            "message": "Update manuscript PDF",
            "tree": pdf_tree["sha"], "parents": [source_sha],
            "author": bot, "committer": bot,
        })
        published_sha = commit["sha"]

    reference_path = base + "/git/ref/heads/" + urllib.parse.quote(branch, safe="")
    head = api.request("GET", reference_path)["object"]["sha"]
    is_current = head in (source_sha, published_sha)
    if head == source_sha and published_sha != source_sha:
        try:
            api.request("PATCH", base + "/git/refs/heads/" + urllib.parse.quote(branch, safe=""), {
                "sha": published_sha, "force": False,
            })
            print("Updated the repository reading copy.")
        except APIError as exc:
            if exc.status not in (409, 422) or api.request("GET", reference_path)["object"]["sha"] == source_sha:
                raise
            is_current = False
            print("A newer manuscript commit arrived; its reading copy was preserved.")
    elif not is_current:
        print("A newer manuscript commit exists; its reading copy was preserved.")
    else:
        print("The repository reading copy is already current.")

    if not is_current:
        print("Skipped release creation for the superseded manuscript commit.")
        return

    try:
        release = api.request("GET", base + "/releases/tags/" + tag)
    except APIError as exc:
        if exc.status != 404:
            raise
        release = None
        page = 1
        while True:
            releases = api.request("GET", base + f"/releases?per_page=100&page={page}")
            release = next((item for item in releases if item["tag_name"] == tag), None)
            if release or len(releases) < 100:
                break
            page += 1
    if release and not release["draft"]:
        print(f"{tag} is already archived; the published version was preserved.")
        return
    if release and release["target_commitish"] != published_sha:
        raise RuntimeError("An unfinished release belongs to another manuscript commit; rerun its original workflow.")

    if release is None:
        try:
            existing_tag = api.request("GET", base + "/git/ref/tags/" + tag)
        except APIError as exc:
            if exc.status != 404:
                raise
        else:
            if existing_tag["object"]["sha"] != published_sha:
                raise RuntimeError("The version tag already identifies another commit; existing history was preserved.")
        release = api.request("POST", base + "/releases", {
            "tag_name": tag, "target_commitish": published_sha,
            "name": title + " — " + tag, "draft": True,
            "body": (
                f"**{title}**\n\n"
                "**GPT-6 Astra**  \nCommunicated and edited by **Boming Jia**\n\n"
                f"[Read PDF](https://github.com/{repository}/blob/{tag}/{filename}) · "
                f"[TeX source](https://github.com/{repository}/tree/{tag}/source)\n\n"
                f"{page_count} {'page' if page_count == 1 else 'pages'}."
            ),
        })
    asset = next((asset for asset in release["assets"] if asset["name"] == filename), None)
    digest = "sha256:" + hashlib.sha256(pdf).hexdigest()
    if asset and asset.get("state") == "starter":
        api.request("DELETE", base + "/releases/assets/" + str(asset["id"]))
        asset = None
    if asset:
        if asset["size"] != len(pdf) or asset.get("digest") not in (None, digest):
            raise RuntimeError("An unfinished release contains a different PDF; no archived file was replaced.")
    else:
        api.request("POST", base + "/releases/" + str(release["id"]) + "/assets?name=" + filename, pdf, binary=True)
    try:
        latest = api.request("GET", base + "/releases/latest")
    except APIError as exc:
        if exc.status != 404:
            raise
        make_latest = True
    else:
        match = re.fullmatch(r"v([0-9]+)\.([0-9]+)\.([0-9]+)", latest["tag_name"])
        make_latest = bool(match) and tuple(map(int, version.split("."))) >= tuple(map(int, match.groups()))
    result = api.request("PATCH", base + "/releases/" + str(release["id"]), {
        "draft": False, "make_latest": "true" if make_latest else "false",
    })
    print("Published " + result["html_url"])


def main():
    version = Path("VERSION").read_text().strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise SystemExit("VERSION must contain a version such as 1.0.1")
    pdf = Path(sys.argv[1]).read_bytes()
    if not pdf.startswith(b"%PDF-"):
        raise SystemExit("The compiled manuscript is not a PDF")
    repository = os.environ["GITHUB_REPOSITORY"]
    source_sha = os.environ["GITHUB_SHA"]
    branch = os.environ["DEFAULT_BRANCH"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise SystemExit("Invalid workflow repository or commit")
    publish(GitHub(os.environ["GH_TOKEN"]), repository, source_sha, branch, version, pdf)


if __name__ == "__main__":
    main()
