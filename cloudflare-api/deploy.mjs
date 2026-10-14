import { writeFile, unlink } from "node:fs/promises";
import { spawn } from "node:child_process";

const required = [
  "RAKUTEN_APPLICATION_ID",
  "RAKUTEN_ACCESS_KEY",
  "RAKUTEN_AFFILIATE_ID",
];

const missing = required.filter((name) => !process.env[name]);
if (missing.length) {
  console.error(`Missing required build secrets: ${missing.join(", ")}`);
  process.exit(1);
}

const secretsPath = `.cloudflare-secrets-${process.pid}.json`;
const secrets = Object.fromEntries(required.map((name) => [name, process.env[name]]));

try {
  await writeFile(secretsPath, JSON.stringify(secrets), { mode: 0o600 });

  const child = spawn(
    "npx",
    ["wrangler", "deploy", "--secrets-file", secretsPath],
    { stdio: "inherit", shell: process.platform === "win32" }
  );

  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("close", resolve);
  });

  if (exitCode !== 0) process.exitCode = exitCode ?? 1;
} finally {
  await unlink(secretsPath).catch(() => {});
}
