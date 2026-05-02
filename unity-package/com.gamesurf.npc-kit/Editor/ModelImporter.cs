// GameSurf NPC Kit — ModelImporter.cs
// Custom asset importer for GGUF and LoRA adapter files.
// Copies models into the correct StreamingAssets/NpcModels/ structure.

using System.IO;
using UnityEditor;
using UnityEngine;

namespace GameSurf.NpcKit.Editor
{
    /// <summary>
    /// Editor utility for importing GGUF models and LoRA adapters into
    /// the correct StreamingAssets directory structure.
    /// </summary>
    public class ModelImporter : EditorWindow
    {
        private string _npcId = "";
        private string _adapterPath = "";
        private string _baseModelPath = "";

        [MenuItem("GameSurf/Import NPC Model")]
        public static void ShowWindow()
        {
            var window = GetWindow<ModelImporter>("Import NPC Model");
            window.minSize = new Vector2(450, 300);
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("Import NPC Model", EditorStyles.boldLabel);
            EditorGUILayout.Space(8);

            // NPC ID
            _npcId = EditorGUILayout.TextField("NPC ID", _npcId);
            if (!string.IsNullOrEmpty(_npcId))
            {
                EditorGUILayout.HelpBox(
                    $"Files will be placed in: StreamingAssets/NpcModels/{_npcId}/",
                    MessageType.Info);
            }

            EditorGUILayout.Space(8);

            // LoRA adapter
            EditorGUILayout.LabelField("LoRA Adapter (.gguf)", EditorStyles.boldLabel);
            EditorGUILayout.BeginHorizontal();
            _adapterPath = EditorGUILayout.TextField(_adapterPath);
            if (GUILayout.Button("Browse", GUILayout.Width(60)))
            {
                string path = EditorUtility.OpenFilePanel("Select LoRA Adapter", "", "gguf");
                if (!string.IsNullOrEmpty(path)) _adapterPath = path;
            }
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(4);

            // Base model (optional)
            EditorGUILayout.LabelField("Base Model (.gguf) — Optional", EditorStyles.boldLabel);
            EditorGUILayout.BeginHorizontal();
            _baseModelPath = EditorGUILayout.TextField(_baseModelPath);
            if (GUILayout.Button("Browse", GUILayout.Width(60)))
            {
                string path = EditorUtility.OpenFilePanel("Select Base Model", "", "gguf");
                if (!string.IsNullOrEmpty(path)) _baseModelPath = path;
            }
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(16);

            // Import button
            EditorGUI.BeginDisabledGroup(
                string.IsNullOrEmpty(_npcId) || string.IsNullOrEmpty(_adapterPath));

            if (GUILayout.Button("Import", GUILayout.Height(32)))
            {
                ImportModel();
            }

            EditorGUI.EndDisabledGroup();
        }

        private void ImportModel()
        {
            string targetDir = Path.Combine(
                Application.streamingAssetsPath, "NpcModels", _npcId);
            Directory.CreateDirectory(targetDir);

            // Copy adapter
            if (!string.IsNullOrEmpty(_adapterPath) && File.Exists(_adapterPath))
            {
                string dest = Path.Combine(targetDir, "adapter_model.gguf");
                File.Copy(_adapterPath, dest, true);
                Debug.Log($"[GameSurf] Copied LoRA adapter to: {dest}");
            }

            // Copy base model
            if (!string.IsNullOrEmpty(_baseModelPath) && File.Exists(_baseModelPath))
            {
                string dest = Path.Combine(targetDir, Path.GetFileName(_baseModelPath));
                File.Copy(_baseModelPath, dest, true);
                Debug.Log($"[GameSurf] Copied base model to: {dest}");
            }

            AssetDatabase.Refresh();
            EditorUtility.DisplayDialog(
                "Import Complete",
                $"NPC model imported to:\nStreamingAssets/NpcModels/{_npcId}/",
                "OK");
        }
    }
}
