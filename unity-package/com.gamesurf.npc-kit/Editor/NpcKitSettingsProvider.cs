// GameSurf NPC Kit — NpcKitSettingsProvider.cs
// Project Settings panel for configuring GameSurf NPC Kit globally.

using UnityEditor;
using UnityEngine;

namespace GameSurf.NpcKit.Editor
{
    public class NpcKitSettingsProvider : SettingsProvider
    {
        private const string SettingsPath = "Project/GameSurf NPC Kit";
        private const string BaseModelPathKey = "GameSurf_BaseModelPath";
        private const string GpuLayersKey = "GameSurf_GpuLayers";
        private const string ContextSizeKey = "GameSurf_ContextSize";
        private const string RemoteServerUrlKey = "GameSurf_RemoteServerUrl";
        private const string UseRemoteKey = "GameSurf_UseRemoteServer";

        public NpcKitSettingsProvider()
            : base(SettingsPath, SettingsScope.Project) { }

        public override void OnGUI(string searchContext)
        {
            EditorGUILayout.LabelField("GameSurf NPC Kit Settings", EditorStyles.boldLabel);
            EditorGUILayout.Space(8);

            // Inference
            EditorGUILayout.LabelField("Inference", EditorStyles.boldLabel);
            bool useRemote = EditorPrefs.GetBool(UseRemoteKey, true);
            useRemote = EditorGUILayout.Toggle("Use Remote Server (dev mode)", useRemote);
            EditorPrefs.SetBool(UseRemoteKey, useRemote);

            if (useRemote)
            {
                string url = EditorPrefs.GetString(RemoteServerUrlKey, "http://127.0.0.1:8000");
                url = EditorGUILayout.TextField("Remote Server URL", url);
                EditorPrefs.SetString(RemoteServerUrlKey, url);
            }
            else
            {
                string modelPath = EditorPrefs.GetString(BaseModelPathKey, "");
                EditorGUILayout.BeginHorizontal();
                modelPath = EditorGUILayout.TextField("Base Model Path", modelPath);
                if (GUILayout.Button("Browse", GUILayout.Width(60)))
                {
                    string path = EditorUtility.OpenFilePanel("Select GGUF Model", "", "gguf");
                    if (!string.IsNullOrEmpty(path)) modelPath = path;
                }
                EditorGUILayout.EndHorizontal();
                EditorPrefs.SetString(BaseModelPathKey, modelPath);

                int gpuLayers = EditorPrefs.GetInt(GpuLayersKey, 32);
                gpuLayers = EditorGUILayout.IntSlider("GPU Layers", gpuLayers, 0, 64);
                EditorPrefs.SetInt(GpuLayersKey, gpuLayers);

                int ctxSize = EditorPrefs.GetInt(ContextSizeKey, 2048);
                ctxSize = EditorGUILayout.IntPopup("Context Size",
                    ctxSize, new[] { "512", "1024", "2048", "4096" }, new[] { 512, 1024, 2048, 4096 });
                EditorPrefs.SetInt(ContextSizeKey, ctxSize);
            }

            EditorGUILayout.Space(12);

            // Model status
            EditorGUILayout.LabelField("Model Discovery", EditorStyles.boldLabel);
            string modelsDir = System.IO.Path.Combine(Application.streamingAssetsPath, "NpcModels");
            if (System.IO.Directory.Exists(modelsDir))
            {
                var dirs = System.IO.Directory.GetDirectories(modelsDir);
                EditorGUILayout.LabelField($"NPC Models Found: {dirs.Length}");
                foreach (string dir in dirs)
                {
                    string npcId = System.IO.Path.GetFileName(dir);
                    bool hasAdapter = System.IO.File.Exists(
                        System.IO.Path.Combine(dir, "adapter_model.gguf"));
                    string status = hasAdapter ? "✓ adapter" : "○ base only";
                    EditorGUILayout.LabelField($"  {npcId}: {status}");
                }
            }
            else
            {
                EditorGUILayout.HelpBox(
                    "No NpcModels/ directory in StreamingAssets.\n" +
                    "Run: gamesurf-train sync --unity-project <path>",
                    MessageType.Info);
            }
        }

        [SettingsProvider]
        public static SettingsProvider CreateProvider()
        {
            return new NpcKitSettingsProvider
            {
                keywords = new[] { "GameSurf", "NPC", "LLM", "LoRA", "dialogue" }
            };
        }
    }
}
