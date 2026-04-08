/**
 * POST /api/bmad-architect-run — Forge: Epic Architect only.
 * Body: `{ "issue_key": "PROJ-1", "target_repo"?: "...", "team_id"?: "..." }`
 */
import { handleForgePost } from "../lib/forge-dispatch.js";

export default async function handler(req: any, res: any): Promise<void> {
  await handleForgePost(req, res, "architect");
}
