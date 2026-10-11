"use strict";
// Output destinations only: never redirect reads or update a reference image.
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
let directory;

function artifactDirectory() {
  if (!directory) {
    const parent = path.join(root, "generated-artifacts", "browser-checks");
    const configured = process.env.HOMENSTAY_OFFLINE_ARTIFACT_DIR;
    if (configured) {
      const configuredParent = path.resolve(configured);
      const relative = path.relative(path.join(root, "generated-artifacts"), configuredParent);
      if (!relative || relative.startsWith("..") || path.isAbsolute(relative))
        throw Error("Capture directory must be a run-specific child of generated-artifacts");
      fs.mkdirSync(configuredParent, { recursive: true });
      directory = fs.mkdtempSync(path.join(configuredParent, "capture-"));
    } else {
      fs.mkdirSync(parent, { recursive: true });
      const name = path.basename(process.argv[1] || "browser", path.extname(process.argv[1] || ""));
      directory = fs.mkdtempSync(path.join(parent, `${name}-`));
    }
    console.log(`CAPTURE_ARTIFACT_DIR: ${directory}`);
  }
  return directory;
}

function artifactPath(requested) {
  const base = artifactDirectory();
  const absolute = path.resolve(requested);
  const inRun = path.relative(base, absolute);
  let relative;
  if (inRun && !inRun.startsWith("..") && !path.isAbsolute(inRun)) {
    relative = inRun;
  } else {
    const inProject = path.relative(root, absolute);
    relative = !inProject.startsWith("..") && !path.isAbsolute(inProject)
      ? inProject : path.join("external", absolute.replace(/^[/\\]+/, ""));
  }
  const destination = path.join(base, relative);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  return destination;
}

module.exports = { artifactDirectory, artifactPath };
