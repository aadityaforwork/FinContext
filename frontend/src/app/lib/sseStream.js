/**
 * SSE stream reader — production-safe replacement for the ad-hoc
 * `chunk.split("\n") + JSON.parse(line)` pattern that breaks on Render.
 *
 * Why the ad-hoc parser breaks:
 *   1. TextDecoder without `{stream: true}` drops/corrupts multi-byte chars
 *      at chunk boundaries.
 *   2. `chunk.split("\n")` discards partial lines — but Render's edge proxy
 *      fragments large SSE events (e.g. our 10-50 KB Context Engine result
 *      payload) across multiple TCP chunks, so a single `data: {...}\n\n`
 *      event arrives as 2-5 chunks. The middle ones JSON.parse-fail and
 *      get silently swallowed by `catch {}`, so the result event is lost
 *      forever and the UI just shows the spinner forever.
 *
 * This helper:
 *   • Buffers raw text across chunks (with streaming TextDecoder)
 *   • Splits ONLY on `\n\n` — the actual SSE event boundary — so a
 *     fragmented event waits in the buffer until it's complete
 *   • Yields one parsed JSON message per complete event (or the raw "[DONE]"
 *     sentinel), so the calling component just does:
 *
 *       for await (const msg of readSSE(response)) {
 *         if (msg === "[DONE]") break;
 *         if (msg.type === "step") ...
 *       }
 *
 * Non-`data:` lines (e.g. `:` heartbeats, `event:`, `id:`) are ignored.
 */

export async function* readSSE(response) {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      // {stream: true} preserves partial multi-byte sequences across chunks.
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line (\n\n). Anything before
      // the last \n\n is a complete event (or events); the remainder stays
      // in the buffer until the next chunk completes it.
      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);

        // Parse the one event. Each event can have multiple data: lines that
        // get concatenated. In our backend we always emit a single data: line
        // per event, but we handle the multi-line case anyway.
        const dataLines = [];
        for (const line of rawEvent.split("\n")) {
          if (line.startsWith("data: ")) dataLines.push(line.slice(6));
          else if (line.startsWith("data:")) dataLines.push(line.slice(5));
        }
        if (dataLines.length === 0) continue;
        const payload = dataLines.join("\n").trim();
        if (!payload) continue;
        if (payload === "[DONE]") {
          yield "[DONE]";
          continue;
        }
        try {
          yield JSON.parse(payload);
        } catch (e) {
          // Malformed JSON event — log so a future regression surfaces. Keep
          // iterating; one bad event shouldn't kill the whole stream.
          // eslint-disable-next-line no-console
          console.warn("[sseStream] dropped malformed event:", e, payload.slice(0, 200));
        }
      }
    }
    // Flush any final buffered data on stream close (server forgot trailing \n\n).
    if (buffer.trim()) {
      for (const line of buffer.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.replace(/^data:\s?/, "").trim();
        if (!payload || payload === "[DONE]") continue;
        try { yield JSON.parse(payload); } catch { /* ignore tail noise */ }
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* ignore */ }
  }
}
