// Layer 1: deterministic rule-based summary. Layer 2: optional LLM rewrite restricted to supplied facts; fails closed.
export function ruleSummary(c) {
  const lv = Object.entries(c.levels).sort((a, b) => b[1] - a[1])[0]?.[0] || "UNKNOWN";
  const svcs = Object.keys(c.services).slice(0, 3).join(", ") || "unknown services";
  const when = c.first_seen ? ` between ${c.first_seen.toISOString().slice(0, 16).replace("T", " ")} and ${c.last_seen.toISOString().slice(11, 16)}` : "";
  const trend = c.trend_ratio > 1.5 ? "increasing" : c.trend_ratio < 0.67 ? "decreasing" : "stable";
  return { text: `${c.size.toLocaleString()} ${lv} events matching "${c.template.slice(0, 100)}" from ${svcs}${when}. Frequency trend is ${trend}.${c.is_anomalous ? " Flagged as anomalous." : ""}`,
    main_pattern: c.template, dominant_level: lv, trend, source: "rule-based" };
}

export async function llmEnhance(summary, c, provider, key) {
  if (!provider || !key) return summary;
  const facts = { name: c.name, size: c.size, template: c.template, levels: c.levels, services: c.services };
  const prompt = `Rewrite this log-cluster summary in 2 sentences for an on-call engineer. Use ONLY these facts; do not invent counts, services, timestamps or causes.\nFACTS: ${JSON.stringify(facts)}\nSUMMARY: ${summary.text}`;
  try {
    let text;
    if (provider === "openai") {
      const r = await fetch("https://api.openai.com/v1/chat/completions", { method: "POST", headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model: "gpt-4o-mini", temperature: 0, messages: [{ role: "user", content: prompt }] }), signal: AbortSignal.timeout(20000) });
      text = (await r.json()).choices[0].message.content;
    } else if (provider === "gemini") {
      const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${key}`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }), signal: AbortSignal.timeout(20000) });
      text = (await r.json()).candidates[0].content.parts[0].text;
    } else return summary;
    return { ...summary, text: text.trim(), source: `llm:${provider}`, rule_text: summary.text };
  } catch { return summary; }
}
