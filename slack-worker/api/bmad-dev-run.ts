/**
 * POST /api/bmad-dev-run — Forge: full dev pipeline on a Story (detect → PR).
 * Body: `{ "issue_key": "PROJ-1", "target_repo"?: "...", "team_id"?: "..." }`
 */
import { handleForgePost } from "../lib/forge-dispatch.js";

export default async function handler(req: any, res: any): Promise<void> {
  await handleForgePost(req, res, "dev");
}
