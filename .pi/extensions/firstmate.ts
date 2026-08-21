// firstmate graph — Pi extension. Loads when Pi starts inside this repo (approve project trust once).
// Gives the captain a banner on deck and two slash commands that never spend a model turn.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function firstmate(pi: ExtensionAPI) {
  const helm = (...args: string[]) => pi.exec("helm", args, { timeout: 15_000 });

  pi.on("session_start", async (_event: unknown, ctx: any) => {
    try {
      const r = await helm("status", "--json");
      if (r.code !== 0) return;
      const s = JSON.parse(r.stdout);
      const items = Object.entries(s.items as Record<string, number>).map(([k, v]) => `${v} ${k}`).join(" · ") || "queue empty";
      const workers = s.herdr_tabs?.length ? `${s.herdr_tabs.filter((t: any) => t.kind === "worker").length} herdr worker tabs` : s.workers ? "workers in background" : "workers stopped";
      ctx?.ui?.notify?.(`⚓ first mate on deck — ${s.projects} project${s.projects === 1 ? "" : "s"} · ${workers} · ${items}  (/fleet · /inbox)`, "info");
    } catch {}
  });

  pi.registerCommand("fleet", {
    description: "Fleet board: workers, projects, queue",
    handler: async (_args: string, ctx: any) => {
      const r = await helm("watch", "--once");
      ctx.ui.notify(r.code === 0 ? r.stdout.trim() : `helm watch failed: ${r.stderr}`, r.code === 0 ? "info" : "warning");
    },
  });

  pi.registerCommand("inbox", {
    description: "What needs the captain: questions, failures, ready branches, open PRs",
    handler: async (_args: string, ctx: any) => {
      const r = await helm("inbox");
      ctx.ui.notify(r.code === 0 ? r.stdout.trim() : `helm inbox failed: ${r.stderr}`, r.code === 0 ? "info" : "warning");
    },
  });
}
