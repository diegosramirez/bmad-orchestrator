/**
 * POST /api/bmad-discovery-run — Forge: Discovery only (check_epic_state + create_or_correct_epic).
 * Body: `{ "issue_key": "PROJ-1", "target_repo"?: "owner/repo", "team_id"?: "SAM1" }`
 * Requires BMAD_FORGE_WEBHOOK_SECRET or BMAD_DISCOVERY_WEBHOOK_SECRET in env.
 */
import { handleForgePost } from "../lib/forge-dispatch.js";

export default async function handler(req: any, res: any): Promise<void> {
  await handleForgePost(req, res, "discovery");
}
