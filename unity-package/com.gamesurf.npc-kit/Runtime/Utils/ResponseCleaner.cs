// GameSurf NPC Kit — ResponseCleaner.cs
// C# port of clean_npc_response() from scripts/llm_integrated_server.py.
// Strips model artifacts, dialogue labels, and ensures clean NPC output.

using System.Text.RegularExpressions;

namespace GameSurf.NpcKit
{
    /// <summary>
    /// Cleans raw LLM output into presentation-ready NPC dialogue.
    /// Ported from Python: scripts/llm_integrated_server.py → clean_npc_response()
    /// </summary>
    public static class ResponseCleaner
    {
        private static readonly string FallbackResponse =
            "I need a moment to gather that thought. Please ask me again.";

        // Cutoff patterns — stop the response when these appear
        private static readonly Regex[] CutoffPatterns = new[]
        {
            new Regex(@"<\|eot_id\|>", RegexOptions.IgnoreCase),
            new Regex(@"<\|start_header_id\|>user<\|end_header_id\|>", RegexOptions.IgnoreCase),
            new Regex(@"<\|start_header_id\|>assistant<\|end_header_id\|>", RegexOptions.IgnoreCase),
            new Regex(@"\nPlayer:", RegexOptions.IgnoreCase),
            new Regex(@"\nAssistant:", RegexOptions.IgnoreCase),
            new Regex(@"\nassistant\s*\nuser:", RegexOptions.IgnoreCase),
            new Regex(@"\nuser:", RegexOptions.IgnoreCase),
            new Regex(@"\nassistant:", RegexOptions.IgnoreCase),
        };

        // Cleanup patterns — remove unwanted prefixes/suffixes
        private static readonly (Regex pattern, string replacement)[] CleanupRules = new[]
        {
            // Remove model-generated extra dialogue turns
            (new Regex(@"\n\s*Player:\s.*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"\n\s*player\s*:.*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"\n\s*User:\s.*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"\n\s*user\s*:.*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),

            // Remove role-prefix artifacts
            (new Regex(@"<\|.*?$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"\b(system|user|assistant)\s*[:\-].*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"\bsystem\s+prompt\s*[:\-].*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"^you are .*?\[MEMORY_CONTEXT.*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"\[MEMORY_CONTEXT\].*$", RegexOptions.IgnoreCase | RegexOptions.Singleline), ""),
            (new Regex(@"^\s*assistant\s*[:\-]?\s*", RegexOptions.IgnoreCase), ""),
            (new Regex(@"^\s*npc\s*[:\-]?\s*", RegexOptions.IgnoreCase), ""),
            (new Regex(@"^\s*NPC\s*[:\-]?\s*", RegexOptions.IgnoreCase), ""),
        };

        /// <summary>
        /// Clean raw LLM output into presentation-ready NPC dialogue.
        /// </summary>
        public static string Clean(string text)
        {
            if (string.IsNullOrWhiteSpace(text))
                return FallbackResponse;

            string cleaned = text.Trim();

            // Strip everything before the assistant header if present
            var assistantHeaderMatch = Regex.Match(
                cleaned,
                @"^.*?<\|start_header_id\|>assistant<\|end_header_id\|>\s*",
                RegexOptions.IgnoreCase | RegexOptions.Singleline
            );
            if (assistantHeaderMatch.Success)
            {
                cleaned = cleaned.Substring(assistantHeaderMatch.Length);
            }

            // Apply cutoff patterns — truncate at first match
            foreach (var pattern in CutoffPatterns)
            {
                var match = pattern.Match(cleaned);
                if (match.Success)
                {
                    cleaned = cleaned.Substring(0, match.Index).Trim();
                    break;
                }
            }

            // Apply cleanup rules
            foreach (var (pattern, replacement) in CleanupRules)
            {
                cleaned = pattern.Replace(cleaned, replacement);
            }

            // Final trim
            cleaned = cleaned.Trim();

            // Fallback if response is too short
            if (string.IsNullOrWhiteSpace(cleaned) || cleaned.Split(' ').Length < 3)
                return FallbackResponse;

            return cleaned;
        }

        /// <summary>
        /// Check if a response contains model-generated dialogue labels.
        /// </summary>
        public static bool HasDialogueLeak(string text)
        {
            if (string.IsNullOrEmpty(text)) return false;

            return Regex.IsMatch(text, @"^(Player|player|User|user)\s*:\s*", RegexOptions.IgnoreCase)
                || Regex.IsMatch(text, @"^(NPC|npc|Assistant|assistant)\s*:\s*", RegexOptions.IgnoreCase)
                || Regex.IsMatch(text, @"\n(PLAYER|Player|User)\s*:\s*\S", RegexOptions.IgnoreCase)
                || Regex.IsMatch(text, @"\n(NPC|Assistant)\s*:\s*\S", RegexOptions.IgnoreCase);
        }
    }
}
