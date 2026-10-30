#!/usr/bin/env node
// Downloads the Wick release this package version points at, checks its hash, and installs the app and the CLI.
// Deliberately no postinstall script: nothing runs unless someone asks for it with `npx wick-mac`.
"use strict";

const { execFileSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { version } = require("../package.json");

const REPOSITORY = "s1lvazxy/wick";
const home = os.homedir();

function option(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function isWritable(directory) {
  try {
    fs.accessSync(directory, fs.constants.W_OK);
    return true;
  } catch {
    return false;
  }
}

function firstWritable(candidates) {
  return candidates.find(isWritable);
}

async function download(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} answered ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
}

async function fetchRelease() {
  const base = `https://github.com/${REPOSITORY}/releases/download/v${version}/Wick-${version}.zip`;
  console.log(`Downloading Wick ${version}…`);
  const [zip, checksum] = await Promise.all([download(base), download(`${base}.sha256`)]);
  const expected = checksum.toString().trim().split(/\s+/)[0];
  const actual = crypto.createHash("sha256").update(zip).digest("hex");
  if (actual !== expected) throw new Error(`Checksum mismatch: expected ${expected}, got ${actual}.`);
  return zip;
}

async function main() {
  if (process.platform !== "darwin") throw new Error("Wick only runs on macOS.");

  const local = option("--from");
  const zip = local ? fs.readFileSync(local) : await fetchRelease();

  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "wick-install-"));
  try {
    const archive = path.join(workspace, "Wick.zip");
    fs.writeFileSync(archive, zip);
    execFileSync("/usr/bin/ditto", ["-x", "-k", archive, workspace]);
    const unpacked = path.join(workspace, "Wick.app");
    execFileSync("/usr/bin/codesign", ["--verify", "--strict", unpacked]);

    let applications = option("--dir");
    if (!applications) {
      const userApplications = path.join(home, "Applications");
      fs.mkdirSync(userApplications, { recursive: true });
      applications = firstWritable(["/Applications", userApplications]);
    }
    const app = path.join(applications, "Wick.app");

    if (!option("--dir")) {
      try {
        execFileSync("/usr/bin/osascript", ["-e", 'quit app id "io.github.s1lvazxy.wick"'], { stdio: "ignore" });
      } catch {}
    }
    fs.rmSync(app, { recursive: true, force: true });
    execFileSync("/usr/bin/ditto", [unpacked, app]);
    console.log(`Installed ${app}`);

    const localBin = path.join(home, ".local", "bin");
    const binDirectory =
      option("--bin-dir") ??
      firstWritable(["/opt/homebrew/bin", "/usr/local/bin"]) ??
      (fs.mkdirSync(localBin, { recursive: true }), localBin);
    const link = path.join(binDirectory, "wick");
    // Only ever replaces its own link. Another program called wick is someone else's.
    let existing = null;
    try {
      existing = fs.lstatSync(link).isSymbolicLink() ? fs.readlinkSync(link) : "not a link";
    } catch {}
    if (existing && !existing.endsWith("/Wick.app/Contents/Helpers/wick")) {
      console.log(`Skipped ${link}: another program is already there. Wick's CLI is in ${app}/Contents/Helpers.`);
    } else {
      fs.rmSync(link, { force: true });
      fs.symlinkSync(path.join(app, "Contents", "Helpers", "wick"), link);
      console.log(`Linked  ${link}`);
    }
    if (!(process.env.PATH ?? "").split(path.delimiter).includes(binDirectory)) {
      console.log(`Add ${binDirectory} to your PATH to use the wick command.`);
    }

    if (!process.argv.includes("--no-open")) execFileSync("/usr/bin/open", [app]);
    console.log("Done. Look for the icon in your menu bar.");
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(`wick-mac: ${error.message}`);
  process.exit(1);
});
