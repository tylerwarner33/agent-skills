---
name: jev-fast-compaction
description: Install and configure the fast-jev-compaction plugin, which replaces the Claude Code compaction summary with Jev keep-or-drop decisions, so /compact finishes in about one second. Includes the changes to use the plugin through Vercel AI Gateway instead of the TypeSafe API. Use when the user asks for faster compaction, Jev compaction, or to set up fast-jev-compaction.
---

# Jev Fast Compaction

The usual compaction sends the full conversation to Claude and asks for a summary. This is slow. The `fast-jev-compaction` plugin asks Jev to make two decisions about each old tool call:

1. Must the tool call stay in the history?
2. Must its result stay verbatim, or can it be cut short?

The plugin keeps the messages that Jev marks as important, word for word. It writes no summary. In the video, compaction took less than one second.

Requires the `jev-setup` skill (a key in the environment).

Upstream plugin: https://github.com/tamaratran/fast-jev-compaction

## How it works

- A hook in the plugin takes control of compaction. The plugin uses function hooks, so `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` must be `1`.
- The newest messages (default 6) are always kept.
- A tool call or result stays if Jev gives a keep probability of 0.5 or more (`keepThreshold`).
- **Fallback:** If Jev cannot reduce the history by at least 25% (`minReductionRatio`), the plugin does not replace the history. The normal Claude compaction runs. Thus, the plugin uses Jev only when it makes a large difference.

## Option A: TypeSafe API key

Use this option when the user has `TYPESAFE_API_KEY`.

1. Add to `~/.claude/settings.json`:

   ```json
   {
     "env": {
       "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"
     }
   }
   ```

   The key must be in `TYPESAFE_API_KEY` (shell or `env` block).

2. Install the plugin:

   ```bash
   claude plugin marketplace add tamaratran/fast-jev-compaction
   claude plugin install fast-jev-compaction@fast-jev-compaction
   ```

3. Restart Claude Code.

## Option B: Vercel AI Gateway (the video setup)

The upstream plugin calls only `https://api.typesafe.ai/v1/systemone` and reads only `TYPESAFE_API_KEY`. To use the gateway, copy the plugin into the project and change it.

1. Clone the plugin into the project, ex. `plugins/fast-jev-compaction/`.
2. Make these changes. Check each file first, because the upstream code can change.
   - `src/request.ts`: `buildJevRequest` already accepts `baseUrl`. Do not change it.
   - `hooks/fast-jev.ts`, `jevAsker`: pass `baseUrl` to `buildJevRequest`. Use `https://ai-gateway.vercel.sh/typesafe/v1/systemone` when the gateway key is in use.
   - `hooks/fast-jev.ts`, `getApiKey`: if `TYPESAFE_API_KEY` is not set, read `AI_GATEWAY_API_KEY`. Return which key was found, so `jevAsker` can select the URL.
   - Model: use `typesafe-ai/jev` for the gateway. Set the plugin `model` option, or change the default when the gateway key is in use.
   - Keep the request body. The gateway accepts the TypeSafe request shape (`noul`, `choice`, `score`).
3. Run the plugin tests (`npm test`). Add one test for the gateway URL and model.
4. Register the local copy as a marketplace and install it:

   ```bash
   claude plugin marketplace add ./plugins/fast-jev-compaction
   claude plugin install fast-jev-compaction@fast-jev-compaction
   ```

5. Set `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` (see Option A). Restart Claude Code.

## Use

Run `/compact` as usual. The plugin hook replaces the normal compaction. The output shows a line such as `fast-jev-compaction: kept N/M messages, no summary`, or a fallback message.

## Plugin options

Set these in the plugin `userConfig`:

| Option | Default | Effect |
| --- | --- | --- |
| `keepThreshold` | 0.5 | Minimum Jev keep probability |
| `preserveRecentMessages` | 6 | Newest messages that are always kept |
| `compactAtPercent` | 60 | Context percentage that starts compaction |
| `minReductionRatio` | 0.25 | Minimum reduction, else normal compaction |
| `truncateHeadChars` | 300 | Characters kept from a cut tool result |
| `model` | `jev-latest` | Jev model id |

## Checks

- After `/compact`, ask Claude about a decision made early in the session. If Claude cannot answer, increase `keepThreshold` or `preserveRecentMessages`.
- If the fallback message shows each time, the session has little to remove. This is correct behavior.
