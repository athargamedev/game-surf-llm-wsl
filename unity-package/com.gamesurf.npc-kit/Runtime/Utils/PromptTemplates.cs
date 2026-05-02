// GameSurf NPC Kit — PromptTemplates.cs
// C# port of llama3_messages_to_prompt() and prompt assembly from
// scripts/llm_integrated_server.py.
// Handles Llama 3.2 chat template formatting and memory slot injection.

using System.Collections.Generic;
using System.Text;

namespace GameSurf.NpcKit
{
    /// <summary>
    /// Chat message for the prompt builder.
    /// </summary>
    public struct ChatMessage
    {
        public string Role;    // "system", "user", "assistant"
        public string Content;

        public ChatMessage(string role, string content)
        {
            Role = role;
            Content = content;
        }

        public static ChatMessage System(string content) => new("system", content);
        public static ChatMessage User(string content) => new("user", content);
        public static ChatMessage Assistant(string content) => new("assistant", content);
    }

    /// <summary>
    /// Llama 3.2 Instruct chat template formatter.
    /// Ported from Python: llama3_messages_to_prompt() + llama3_completion_to_prompt()
    /// </summary>
    public static class PromptTemplates
    {
        // Llama 3 special tokens
        private const string BeginOfText = "<|begin_of_text|>";
        private const string StartHeaderId = "<|start_header_id|>";
        private const string EndHeaderId = "<|end_header_id|>";
        private const string EotId = "<|eot_id|>";

        /// <summary>
        /// Stop strings — the model should stop generating when these appear.
        /// Pass these to the llama.cpp sampling parameters.
        /// </summary>
        public static readonly string[] StopStrings = new[]
        {
            EotId,
            $"{StartHeaderId}user{EndHeaderId}",
            $"{StartHeaderId}assistant{EndHeaderId}",
            "\nuser:",
            "\nPlayer:",
            "\nassistant:",
            "\nAssistant:",
            "\nassistant\nuser:",
        };

        /// <summary>
        /// Format a list of chat messages into a Llama 3.2 instruct prompt string.
        /// Equivalent to Python llama3_messages_to_prompt().
        /// </summary>
        public static string FormatMessages(IList<ChatMessage> messages)
        {
            var sb = new StringBuilder(2048);
            sb.Append(BeginOfText);

            foreach (var msg in messages)
            {
                sb.Append(StartHeaderId);
                sb.Append(msg.Role);
                sb.Append(EndHeaderId);
                sb.Append("\n\n");
                sb.Append(msg.Content.Trim());
                sb.Append(EotId);
            }

            // Append assistant header to trigger generation
            sb.Append(StartHeaderId);
            sb.Append("assistant");
            sb.Append(EndHeaderId);
            sb.Append("\n\n");

            return sb.ToString();
        }

        /// <summary>
        /// Format a simple completion prompt (user message only, no system prompt).
        /// Equivalent to Python llama3_completion_to_prompt().
        /// </summary>
        public static string FormatCompletion(string userMessage)
        {
            return
                BeginOfText +
                StartHeaderId + "user" + EndHeaderId + "\n\n" +
                userMessage.Trim() + EotId +
                StartHeaderId + "assistant" + EndHeaderId + "\n\n";
        }

        /// <summary>
        /// Build a full prompt for NPC dialogue including system prompt and history.
        /// </summary>
        /// <param name="profile">The NPC profile</param>
        /// <param name="memoryContext">Player memory context (or null)</param>
        /// <param name="playerMessage">Current player message</param>
        /// <param name="history">Prior conversation turns</param>
        /// <param name="maxHistoryTurns">Max recent turns to include (default 6)</param>
        public static string BuildNpcPrompt(
            NpcProfile profile,
            string memoryContext,
            string playerMessage,
            IList<ChatMessage> history = null,
            int maxHistoryTurns = 6)
        {
            var messages = new List<ChatMessage>();

            // 1. System prompt with memory injection
            string systemPrompt = profile.BuildSystemPrompt(memoryContext);
            messages.Add(ChatMessage.System(systemPrompt));

            // 2. Recent conversation history (trimmed to maxHistoryTurns)
            if (history != null && history.Count > 0)
            {
                int startIdx = history.Count > maxHistoryTurns * 2
                    ? history.Count - maxHistoryTurns * 2
                    : 0;
                for (int i = startIdx; i < history.Count; i++)
                {
                    messages.Add(history[i]);
                }
            }

            // 3. Current player message
            messages.Add(ChatMessage.User(playerMessage));

            return FormatMessages(messages);
        }

        /// <summary>
        /// Apply the memory slot placeholder in a system prompt.
        /// Equivalent to Python apply_memory_slot().
        /// </summary>
        public static string ApplyMemorySlot(string systemPrompt, string memoryContext)
        {
            const string placeholder = "[MEMORY_CONTEXT: {player_memory_summary}]";

            if (string.IsNullOrEmpty(memoryContext))
            {
                string noMemory = "[MEMORY_CONTEXT]\nNo saved player memory.";
                return systemPrompt.Replace(placeholder, noMemory);
            }

            string memoryBlock =
                "[MEMORY_CONTEXT]\n" + memoryContext + "\n\n" +
                "[MEMORY_RULE]\n" +
                "Use Recent NPC Memories as player-specific context. If the player asks " +
                "about a previous or last conversation, answer from this memory and do " +
                "not claim you have no memory.";

            return systemPrompt.Replace(placeholder, memoryBlock);
        }
    }
}
