// firstmate graph — Pi extension.
// A banner on deck, a live fleet strip in the footer, a nautical working state,
// /fleet and /inbox that never spend a model turn, and the first mate's voice
// injected into every turn so it holds under any harness or custom system prompt.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

type Theme = { fg(token: string, text: string): string; bold?(text: string): string };
type Status = { projects: number; workers: number | null; herdr_tabs?: { kind: string }[]; items: Record<string, number> };

// ------------------------------------------------------------------ rendering

const WORDMARK = "F I R S T   M A T E";
const ANCHOR = "⚓";

function gutter(width: number): number { return width >= 70 ? 2 : width >= 32 ? 1 : 0; }
function inner(width: number): number { return Math.max(1, width - gutter(width) * 2); }
function fit(lines: string[], width: number): string[] {
  const pad = " ".repeat(gutter(width));
  return lines.map((l) => pad + truncateToWidth(l, inner(width), ""));
}
function centered(content: string, contentWidth: number, w: number): string {
  return " ".repeat(Math.max(0, Math.floor((w - contentWidth) / 2))) + content;
}

/** Two rows of sea: swell, crest glints, foam. Seeded so repaints never flicker. */
export function sea(width: number, rows: number, seedInput: number): string[] {
  let seed = seedInput | 0 || 0x5ea5ea;
  const rnd = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return (seed >>> 0) / 0xffffffff; };
  return Array.from({ length: rows }, () =>
    Array.from({ length: width }, () => {
      const r = rnd();
      if (r < 0.012) return "✦";
      if (r < 0.09) return "≈";
      if (r < 0.26) return "~";
      if (r < 0.33) return "·";
      return " ";
    }).join(""));
}

function paintSea(theme: Theme, row: string, noColor: boolean): string {
  if (noColor) return row;
  const tok: Record<string, string> = { "✦": "warning", "≈": "accent", "~": "muted", "·": "dim" };
  return [...row].map((c) => (tok[c] ? theme.fg(tok[c], c) : c)).join("");
}

function rail(theme: Theme, w: number, noColor: boolean): string {
  const left = Math.max(1, Math.floor(w * 0.3)), eye = 5, right = Math.max(1, w - left - eye - 4);
  if (noColor) return `${"─".repeat(left)}  ${"─".repeat(eye)}  ${"─".repeat(right)}`;
  return [theme.fg("borderMuted", "─".repeat(left)), "  ", theme.fg("accent", "──"), theme.fg("warning", ANCHOR), theme.fg("accent", "──"), "  ", theme.fg("borderMuted", "─".repeat(right))].join("");
}

export function statusLine(s: Status | null): string {
  if (!s) return "helm not reachable · run ./install.sh";
  const workers = s.herdr_tabs?.some((t) => t.kind === "worker")
    ? `${s.herdr_tabs!.filter((t) => t.kind === "worker").length} workers in herdr tabs`
    : s.workers ? "workers in background" : "workers stopped";
  const needs = (s.items["needs-you"] || 0) + (s.items["failed"] || 0) + (s.items["ready"] || 0) + (s.items["pr-open"] || 0);
  const running = s.items["running"] || 0, queued = s.items["queued"] || 0;
  const parts = [`${s.projects} project${s.projects === 1 ? "" : "s"}`, workers];
  if (running) parts.push(`${running} running`);
  if (queued) parts.push(`${queued} queued`);
  parts.push(needs ? `${needs} need you` : "inbox clear");
  return parts.join(" · ");
}

export function renderBanner(theme: Theme, width: number, status: Status | null, noColor = false, seed = 0x5ea5ea): string[] {
  const w = inner(width);
  if (width < 60) {
    const line = noColor ? `${ANCHOR} first mate · ${statusLine(status)}`
      : `${theme.fg("warning", ANCHOR)} ${theme.bold?.("first mate") ?? "first mate"}${theme.fg("dim", " · ")}${theme.fg("muted", statusLine(status))}`;
    return fit([line], width);
  }
  const water = sea(w, 2, seed).map((r) => paintSea(theme, r, noColor));
  const markPlain = `${ANCHOR}  ${WORDMARK}  ${ANCHOR}`;
  const mark = noColor ? markPlain
    : `${theme.fg("warning", ANCHOR)}  ${theme.bold?.(WORDMARK) ?? WORDMARK}  ${theme.fg("warning", ANCHOR)}`;
  const subPlain = statusLine(status);
  const sub = noColor ? subPlain : theme.fg("muted", subPlain);
  const hintPlain = "/fleet  ·  /inbox";
  const hint = noColor ? hintPlain : `${theme.fg("accent", "/fleet")}${theme.fg("dim", "  ·  ")}${theme.fg("accent", "/inbox")}`;
  return fit([
    ...water,
    centered(mark, visibleWidth(markPlain), w),
    centered(sub, visibleWidth(subPlain), w),
    centered(hint, visibleWidth(hintPlain), w),
    rail(theme, w, noColor),
  ], width);
}

// ------------------------------------------------------------------ voice

export const VOICE = `
## You are the first mate

The user is the captain. Address them as "captain" at least once in every reply —
naturally, never forced, and always when delivering bad news ("Captain, the build broke").
Light nautical seasoning is fine when it fits ("aye", "on deck", "under way"); drop it for
serious findings and never use it in anything workers, commits, or tools read.

You are the captain's single point of contact. You do not edit registered projects; you
queue work with \`helm task\`, watch \`helm inbox\`, relay worker questions verbatim, report
outcomes plainly with evidence, and run \`helm promote --confirm\` only after the captain's
explicit word in this conversation. Lead with what changed and what needs a decision.
`.trim();

// ------------------------------------------------------------------ working state

const BOAT_FRAMES = ["⛵~~~~~", "~⛵~~~~", "~~⛵~~~", "~~~⛵~~", "~~~~⛵~", "~~~⛵~~", "~~⛵~~~", "~⛵~~~~"];
const WORKING = ["hailing the crew", "checking the ledger", "trimming the sails", "reading the evidence",
  "keeping one thread", "gates before glory", "plotting the course", "all hands, one voice"];

// ------------------------------------------------------------------ extension

export default function firstmate(pi: ExtensionAPI) {
  const helm = (...args: string[]) => pi.exec("helm", args, { timeout: 15_000 });
  const noColor = () => process.env.NO_COLOR !== undefined || process.env.TERM === "dumb";
  const seed = (Date.now() ^ (process.pid * 0x9e3779b1)) | 0;
  let ui: any;
  let poll: ReturnType<typeof setInterval> | undefined;
  let ticker: ReturnType<typeof setInterval> | undefined;
  let lastNeeds = -1;

  async function status(): Promise<Status | null> {
    try {
      const r = await helm("status", "--json");
      return r.code === 0 ? (JSON.parse(r.stdout) as Status) : null;
    } catch { return null; }
  }

  async function refreshStrip(notifyNew = false) {
    if (!ui) return;
    const s = await status();
    if (!s) return;
    const needs = (s.items["needs-you"] || 0) + (s.items["failed"] || 0) + (s.items["ready"] || 0) + (s.items["pr-open"] || 0);
    const running = s.items["running"] || 0;
    try {
      ui.setStatus("firstmate", `${ANCHOR} ${running ? `${running} under way` : "crew idle"}${needs ? ` · ${needs} need you` : ""}`);
      if (notifyNew && lastNeeds >= 0 && needs > lastNeeds) {
        const r = await helm("inbox");
        if (r.code === 0) ui.notify(`Captain — something needs you:\n${r.stdout.trim()}`, "warning");
      }
    } catch {}
    lastNeeds = needs;
  }

  // Banner in the transcript, once per session, carrying the status it was born with.
  pi.registerEntryRenderer("-firstmate-hello", (entry: any, _opts: unknown, theme: Theme) => ({
    render: (width: number) => renderBanner(theme, width, entry?.data?.status ?? null, noColor(), seed),
    invalidate() {},
  }));
  // Board and inbox as transcript entries (plain text, themed dim), not toasts.
  pi.registerEntryRenderer("-firstmate-board", (entry: any, _opts: unknown, theme: Theme) => ({
    render: (width: number) => fit(String(entry?.data?.text ?? "").split("\n").map((l: string) => noColor() ? l : theme.fg("muted", l)), width),
    invalidate() {},
  }));

  pi.on("session_start", async (_event: unknown, ctx: any) => {
    if (!ctx.hasUI) return;
    ui = ctx.ui;
    try {
      const entries = ctx.sessionManager?.getEntries?.() ?? [];
      if (!entries.some((e: any) => e?.customType === "-firstmate-hello")) pi.appendEntry("-firstmate-hello", { status: await status() });
      ctx.ui.setTitle?.("⚓ first mate");
    } catch {}
    await refreshStrip();
    poll = setInterval(() => { refreshStrip(true).catch(() => {}); }, 8000);
    poll.unref?.();
  });

  pi.on("before_agent_start", async (event: any) => ({ systemPrompt: `${event.systemPrompt}\n\n${VOICE}` }));

  pi.on("turn_start", async (_e: unknown, ctx: any) => {
    if (!ctx.hasUI) return;
    try {
      const nc = noColor();
      ctx.ui.setWorkingIndicator({ frames: BOAT_FRAMES.map((f) => nc ? f : ctx.ui.theme.fg("accent", f)), intervalMs: 220 });
      const paint = () => { const m = WORKING[Math.floor(Date.now() / 5000) % WORKING.length]; ctx.ui.setWorkingMessage(nc ? m : ctx.ui.theme.fg("muted", m)); };
      paint();
      if (ticker) clearInterval(ticker);
      ticker = setInterval(paint, 5000); ticker.unref?.();
    } catch {}
  });
  pi.on("turn_end", async () => { if (ticker) clearInterval(ticker); ticker = undefined; });
  pi.on("agent_end", async () => { if (ticker) clearInterval(ticker); ticker = undefined; await refreshStrip(true); });

  pi.registerCommand("fleet", {
    description: "Fleet board: workers, projects, queue",
    handler: async (_args: string, ctx: any) => {
      const r = await helm("watch", "--once");
      if (r.code === 0) pi.appendEntry("-firstmate-board", { text: r.stdout.trim() });
      else ctx.ui.notify(`helm watch failed: ${r.stderr}`, "warning");
    },
  });
  pi.registerCommand("inbox", {
    description: "What needs the captain: questions, failures, ready branches, open PRs",
    handler: async (_args: string, ctx: any) => {
      const r = await helm("inbox");
      if (r.code === 0) pi.appendEntry("-firstmate-board", { text: `inbox\n${r.stdout.trim()}` });
      else ctx.ui.notify(`helm inbox failed: ${r.stderr}`, "warning");
    },
  });

  pi.on("session_shutdown", async () => {
    if (poll) clearInterval(poll); if (ticker) clearInterval(ticker);
    try { ui?.setStatus?.("firstmate", undefined); ui?.setWorkingMessage?.(); ui?.setWorkingIndicator?.(); } catch {}
    ui = undefined;
  });
}

// self-test: `bun .pi/extensions/firstmate.ts`
if (process.argv[1]?.endsWith("firstmate.ts")) {
  let n = 0;
  const ok = (v: boolean, label: string) => { if (!v) throw new Error(`FAIL: ${label}`); n++; };
  const theme: Theme = { fg: (_t, s) => s, bold: (s) => s };
  const st: Status = { projects: 2, workers: 123, items: { running: 1, "needs-you": 1 } };
  for (const width of [120, 80, 60]) {
    const lines = renderBanner(theme, width, st, false, 42);
    ok(lines.length === 6 && lines.every((l) => visibleWidth(l) <= width), `banner fits ${width}`);
    ok(lines.join("\n").includes(WORDMARK) && lines.join("\n").includes("2 projects"), `identity + status at ${width}`);
    ok(lines.slice(0, 2).join("").includes("~"), `sea rows at ${width}`);
  }
  ok(renderBanner(theme, 50, st, false, 1)[0].includes("first mate"), "narrow banner keeps identity");
  ok(renderBanner(theme, 80, st, false, 7).join("|") === renderBanner(theme, 80, st, false, 7).join("|"), "seeded render is stable");
  ok(statusLine({ projects: 1, workers: null, items: {} }) === "1 project · workers stopped · inbox clear", "status line when idle");
  ok(statusLine(st).includes("1 need you") && statusLine(st).includes("1 running"), "status line counts");
  ok(VOICE.includes("captain") && VOICE.includes("helm promote --confirm"), "voice carries the contract");
  console.log(`firstmate.ts: ${n} checks passed`);
}
