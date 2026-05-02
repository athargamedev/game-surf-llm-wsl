// GameSurf NPC Kit — NpcProfile.cs
// ScriptableObject that defines an NPC's identity, personality, and model configuration.
// Ported from the Python NPC profiles system (datasets/configs/npc_profiles.json).

using System;
using UnityEngine;

namespace GameSurf.NpcKit
{
    /// <summary>
    /// Personality configuration for an NPC — tone, refusal style, and behavior rules.
    /// </summary>
    [Serializable]
    public class PersonalityConfig
    {
        [Tooltip("Overall conversational tone (e.g., 'warm and enthusiastic', 'scholarly')")]
        public string tone = "friendly and knowledgeable";

        [Tooltip("How the NPC handles off-topic questions")]
        public string refusalStyle = "briefly redirect back to your subject";

        [Tooltip("Teaching or interaction style")]
        public string teachingStyle = "conversational";
    }

    /// <summary>
    /// ScriptableObject that fully describes an NPC character for the GameSurf system.
    /// Create via: Assets > Create > GameSurf > NPC Profile
    /// </summary>
    [CreateAssetMenu(fileName = "NewNpcProfile", menuName = "GameSurf/NPC Profile", order = 1)]
    public class NpcProfile : ScriptableObject
    {
        [Header("Identity")]
        [Tooltip("Unique NPC identifier (kebab_case, e.g. 'jazz_history_instructor')")]
        public string npcId;

        [Tooltip("Display name shown in dialogue UI")]
        public string displayName;

        [Tooltip("NPC scope/role (e.g. 'instructor', 'merchant', 'quest_giver')")]
        public string npcScope = "instructor";

        [Header("Knowledge Domain")]
        [Tooltip("Primary subject this NPC covers")]
        public string subject;

        [Tooltip("Specific sub-focus within the subject")]
        public string subjectFocus;

        [Tooltip("List of specific domain knowledge areas")]
        public string[] domainKnowledge;

        [Header("Personality")]
        public PersonalityConfig personality;

        [Tooltip("Voice/behavior rules injected into the system prompt")]
        [TextArea(2, 5)]
        public string[] voiceRules;

        [Header("System Prompt")]
        [Tooltip("Custom system prompt template. Use {display_name}, {subject}, {memory_slot}, {voice_rules} as placeholders.")]
        [TextArea(5, 15)]
        public string systemPromptTemplate =
            "You are {display_name}. {memory_slot} " +
            "Subject boundary: {subject}. " +
            "{voice_rules} " +
            "If the user asks outside this subject, do not answer the off-topic request; {refusal_style}. " +
            "When MEMORY_CONTEXT contains a relevant prior topic and the user asks to remember or continue, " +
            "name that topic and add one new concrete subject fact. " +
            "Answer in 1-3 sentences. Do NOT write 'Player:' or 'NPC:' labels. " +
            "Stop immediately after answering. Do not add follow-up questions.";

        [Header("Model Configuration")]
        [Tooltip("Path to LoRA adapter file relative to StreamingAssets/NpcModels/")]
        public string loraAdapterPath;

        [Tooltip("Whether this NPC is currently active and available for dialogue")]
        public bool isActive = true;

        /// <summary>
        /// Build the runtime system prompt with all placeholders resolved.
        /// </summary>
        public string BuildSystemPrompt(string memoryContext = null)
        {
            string voiceRulesText = voiceRules != null && voiceRules.Length > 0
                ? string.Join(" ", System.Array.ConvertAll(voiceRules, r => $"- {r}"))
                : "";

            string memorySlot = string.IsNullOrEmpty(memoryContext)
                ? "[MEMORY_CONTEXT]\nNo saved player memory."
                : $"[MEMORY_CONTEXT]\n{memoryContext}\n\n" +
                  "[MEMORY_RULE]\n" +
                  "Use Recent NPC Memories as player-specific context. If the player asks " +
                  "about a previous or last conversation, answer from this memory and do " +
                  "not claim you have no memory.";

            // Strip honorific prefixes to avoid "I am Professor Professor" pattern
            string cleanName = displayName;
            if (cleanName.StartsWith("Professor ", StringComparison.OrdinalIgnoreCase))
                cleanName = cleanName.Substring(10);
            else if (cleanName.StartsWith("Dr. ", StringComparison.OrdinalIgnoreCase))
                cleanName = cleanName.Substring(4);
            else if (cleanName.StartsWith("Doctor ", StringComparison.OrdinalIgnoreCase))
                cleanName = cleanName.Substring(7);

            return systemPromptTemplate
                .Replace("{display_name}", cleanName)
                .Replace("{subject}", subject ?? "")
                .Replace("{memory_slot}", memorySlot)
                .Replace("{voice_rules}", voiceRulesText)
                .Replace("{refusal_style}", personality?.refusalStyle ?? "briefly redirect back to your subject");
        }

        /// <summary>
        /// Get the full LoRA adapter path under StreamingAssets.
        /// </summary>
        public string GetLoraAdapterFullPath()
        {
            if (string.IsNullOrEmpty(loraAdapterPath))
                return null;

            return System.IO.Path.Combine(
                Application.streamingAssetsPath,
                "NpcModels",
                npcId,
                loraAdapterPath
            );
        }
    }
}
