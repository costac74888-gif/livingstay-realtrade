"""Export exact Git Data API objects. No network, credentials, or ref writes."""
import argparse
import base64
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def person(value):
    match = re.fullmatch(r"(.*) <([^<>]*)> (-?\d+) ([+-]\d{4})", value)
    if not match or match[4] == "-0000":
        raise ValueError("Unsupported identity/timezone; no ref update")
    offset = match[4]
    minutes = (int(offset[1:3]) * 60 + int(offset[3:])) * (
        1 if offset[0] == "+" else -1)
    tz = datetime.timezone(datetime.timedelta(minutes=minutes))
    return {"name": match[1], "email": match[2],
            "date": datetime.datetime.fromtimestamp(int(match[3]), tz).isoformat()}


def export(repo, base, tip, owner, repository, branch, main):
    if not re.fullmatch(r"development/[A-Za-z0-9._/-]+", branch):
        raise ValueError("Only explicit development/* branches are permitted")
    if git(repo, "rev-parse", "--show-object-format").strip() != b"sha1":
        raise ValueError("GitHub backup requires SHA-1 objects")
    base = git(repo, "rev-parse", base + "^{commit}").decode().strip()
    tip = git(repo, "rev-parse", tip + "^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", main):
        raise ValueError("Expected main SHA is required")
    subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base, tip],
                   check=True, stdout=subprocess.DEVNULL)
    objects, seen = [], set()

    def add(kind, sha, payload):
        raw = git(repo, "cat-file", kind, sha)
        digest = hashlib.sha1(kind.encode() + b" " + str(len(raw)).encode()
                              + b"\0" + raw).hexdigest()
        if digest != sha:
            raise ValueError("Local object hash mismatch")
        objects.append({"type": kind, "sha": sha, "payload": payload,
                        "raw": base64.b64encode(raw).decode("ascii")})
        seen.add(sha)

    def tree(sha):
        if sha in seen:
            return
        entries = []
        for record in git(repo, "ls-tree", "-z", sha).split(b"\0"):
            if not record:
                continue
            meta, name = record.split(b"\t", 1)
            mode, kind, child = meta.decode("ascii").split()
            path = name.decode("utf-8")  # No replacement decoding of Git names.
            if kind == "tree":
                tree(child)
            elif kind == "blob" and child not in seen:
                content = git(repo, "cat-file", "blob", child)
                add("blob", child, {"encoding": "base64",
                                   "content": base64.b64encode(content).decode("ascii")})
            elif kind not in ("blob", "commit"):
                raise ValueError("Unsupported tree entry")
            entries.append({"path": path, "mode": mode, "type": kind, "sha": child})
        # Empty trees must be found/reused remotely rather than POSTing [] (422).
        add("tree", sha, {"tree": entries})

    commit_shas = git(repo, "rev-list", "--reverse", "--topo-order",
                      base + ".." + tip).decode().splitlines()
    boundaries = {base}
    # Complete trees (not diffs) preserve deletes, modes, symlinks and gitlinks.
    # Deduplicate content-addressed objects across all commits, including empty commits.
    for sha in commit_shas:
        header, message = git(repo, "cat-file", "commit", sha).split(b"\n\n", 1)
        payload = {"message": message.decode("utf-8"), "parents": []}
        keys = []
        for line in header.decode("utf-8").split("\n"):
            key, value = line.split(" ", 1)
            keys.append(key)
            if key == "parent":
                payload["parents"].append(value)
            elif key == "tree":
                payload["tree"] = value
            elif key in ("author", "committer"):
                payload[key] = person(value)
            else:
                raise ValueError("Unsupported commit header; no ref update")
        if keys != ["tree"] + ["parent"] * len(payload["parents"]) + ["author", "committer"]:
            raise ValueError("Unsupported commit header order; no ref update")
        for parent in payload["parents"]:
            if parent not in commit_shas:
                subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                                parent, base], check=True, stdout=subprocess.DEVNULL)
                boundaries.add(parent)
        tree(payload["tree"])
        add("commit", sha, payload)
    return {"version": 1, "owner": owner, "repository": repository, "branch": branch,
            "expectedDev": base, "expectedMain": main, "tip": tip,
            "boundaries": sorted(boundaries), "objects": objects}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True, help="Expected remote development SHA")
    parser.add_argument("--tip", default="HEAD")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--output", required=True,
                        help="Private generated-artifacts/*.json path (never commit)")
    args = parser.parse_args()
    path = Path(args.output)
    if "generated-artifacts" not in path.parts:
        parser.error("Output must be under ignored generated-artifacts/")
    manifest = export(args.repo, args.base, args.tip, args.owner, args.repository,
                      args.branch, args.expected_main)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids accidentally replacing an in-progress export.
    with path.open("x", encoding="utf-8") as stream:
        path.chmod(0o600)
        json.dump(manifest, stream, ensure_ascii=False)
    print(f"Exported {len(manifest['objects'])} exact objects; no remote changes")


if __name__ == "__main__":
    main()
