/**
 * GitHub App authentication for the webhook-worker.
 *
 * Replaces the previous PAT (BMAD_GITHUB_TOKEN / GITHUB_TOKEN) with installation
 * tokens minted by @octokit/auth-app. The library handles JWT signing, token
 * caching, and refresh internally.
 */
import { readFileSync } from "node:fs";

import { createAppAuth } from "@octokit/auth-app";

export interface GitHubAuth {
  /** Returns a fresh installation access token. */
  getToken(): Promise<string>;
  /** Returns the full Authorization header value (`token <…>`). */
  getAuthHeader(): Promise<string>;
}

let cached: GitHubAuth | null = null;

function loadPrivateKey(): string {
  const path = process.env.BMAD_GITHUB_APP_PRIVATE_KEY_PATH?.trim();
  if (path) {
    return readFileSync(path, "utf8");
  }
  const inline = process.env.BMAD_GITHUB_APP_PRIVATE_KEY?.trim();
  if (inline) {
    // Allow `\n`-escaped PEMs from K8s/Cloud Run env vars.
    return inline.replace(/\\n/g, "\n");
  }
  throw new Error(
    "GitHub App authentication requires BMAD_GITHUB_APP_PRIVATE_KEY or " +
      "BMAD_GITHUB_APP_PRIVATE_KEY_PATH to be set."
  );
}

function buildAuth(): GitHubAuth {
  const appId = process.env.BMAD_GITHUB_APP_ID?.trim();
  const installationId = process.env.BMAD_GITHUB_APP_INSTALLATION_ID?.trim();
  if (!appId || !installationId) {
    throw new Error(
      "GitHub App authentication requires BMAD_GITHUB_APP_ID and " +
        "BMAD_GITHUB_APP_INSTALLATION_ID to be set."
    );
  }
  const privateKey = loadPrivateKey();
  if (!privateKey.startsWith("-----BEGIN")) {
    throw new Error(
      "BMAD_GITHUB_APP_PRIVATE_KEY must be a PEM-encoded RSA key " +
        "(should start with '-----BEGIN')."
    );
  }

  const auth = createAppAuth({
    appId,
    privateKey,
    installationId,
  });

  async function getToken(): Promise<string> {
    const { token } = await auth({ type: "installation" });
    return token;
  }

  async function getAuthHeader(): Promise<string> {
    return `token ${await getToken()}`;
  }

  return { getToken, getAuthHeader };
}

/**
 * Returns the process-wide GitHub auth singleton, building it on first call.
 * Calling this at server startup makes config errors fail fast at boot.
 */
export function getGitHubAuth(): GitHubAuth {
  if (cached === null) {
    cached = buildAuth();
  }
  return cached;
}

export function resetGitHubAuthForTests(): void {
  cached = null;
}
