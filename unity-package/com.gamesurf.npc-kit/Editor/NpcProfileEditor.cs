// GameSurf NPC Kit — NpcProfileEditor.cs
// Custom inspector for NpcProfile ScriptableObjects.

using UnityEngine;
using UnityEditor;

namespace GameSurf.NpcKit.Editor
{
    [CustomEditor(typeof(NpcProfile))]
    public class NpcProfileEditor : UnityEditor.Editor
    {
        private bool _showPromptPreview;

        public override void OnInspectorGUI()
        {
            var profile = (NpcProfile)target;

            // Header
            EditorGUILayout.LabelField("GameSurf NPC Profile", EditorStyles.boldLabel);
            EditorGUILayout.Space(4);

            // Status badge
            var statusColor = profile.isActive ? Color.green : Color.gray;
            var statusText = profile.isActive ? "● Active" : "○ Inactive";
            var style = new GUIStyle(EditorStyles.label) { normal = { textColor = statusColor } };
            EditorGUILayout.LabelField(statusText, style);
            EditorGUILayout.Space(4);

            DrawDefaultInspector();

            EditorGUILayout.Space(8);

            // Prompt preview
            _showPromptPreview = EditorGUILayout.Foldout(_showPromptPreview, "System Prompt Preview");
            if (_showPromptPreview)
            {
                EditorGUI.indentLevel++;
                string preview = profile.BuildSystemPrompt("(sample memory context)");
                EditorGUILayout.TextArea(preview, EditorStyles.wordWrappedLabel);
                EditorGUI.indentLevel--;
            }

            EditorGUILayout.Space(4);

            // Validation
            if (string.IsNullOrEmpty(profile.npcId))
                EditorGUILayout.HelpBox("NPC ID is required.", MessageType.Error);
            if (string.IsNullOrEmpty(profile.displayName))
                EditorGUILayout.HelpBox("Display Name is required.", MessageType.Warning);
            if (string.IsNullOrEmpty(profile.subject))
                EditorGUILayout.HelpBox("Subject is required for proper dialogue boundaries.", MessageType.Warning);

            // LoRA adapter status
            if (!string.IsNullOrEmpty(profile.loraAdapterPath))
            {
                string fullPath = profile.GetLoraAdapterFullPath();
                if (fullPath != null && System.IO.File.Exists(fullPath))
                {
                    var fileInfo = new System.IO.FileInfo(fullPath);
                    float sizeMB = fileInfo.Length / (1024f * 1024f);
                    EditorGUILayout.HelpBox(
                        $"LoRA adapter found: {sizeMB:F1} MB",
                        MessageType.Info
                    );
                }
                else
                {
                    EditorGUILayout.HelpBox(
                        $"LoRA adapter not found at: {fullPath}\nRun gamesurf-train to generate it.",
                        MessageType.Warning
                    );
                }
            }
        }
    }
}
