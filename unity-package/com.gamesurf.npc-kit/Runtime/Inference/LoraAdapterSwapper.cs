// GameSurf NPC Kit — LoraAdapterSwapper.cs
// Manages LoRA adapter hot-swapping for multiple NPCs sharing one base model.
// Ported from: llm_integrated_server.py → select_npc_runtime() + preload logic.

using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace GameSurf.NpcKit
{
    /// <summary>
    /// Manages LoRA adapter lifecycle for multiple NPC characters sharing
    /// a single base GGUF model. Supports hot-swapping adapters at runtime
    /// with minimal latency.
    /// </summary>
    public class LoraAdapterSwapper : IDisposable
    {
        private readonly LlamaCppModel _model;
        private readonly Dictionary<string, string> _adapterPaths = new();
        private string _activeNpcId;
        private bool _disposed;

        /// <summary>Currently active NPC ID, or null if using base model.</summary>
        public string ActiveNpcId => _activeNpcId;

        /// <summary>Number of registered NPC adapters.</summary>
        public int RegisteredAdapterCount => _adapterPaths.Count;

        public LoraAdapterSwapper(LlamaCppModel model)
        {
            _model = model ?? throw new ArgumentNullException(nameof(model));
        }

        /// <summary>
        /// Register an NPC's LoRA adapter path for later activation.
        /// Does not load the adapter until SwitchToNpc() is called.
        /// </summary>
        public void RegisterAdapter(string npcId, string adapterPath)
        {
            if (string.IsNullOrEmpty(npcId))
                throw new ArgumentException("npcId cannot be null or empty");

            if (string.IsNullOrEmpty(adapterPath) || !File.Exists(adapterPath))
            {
                Debug.LogWarning($"[GameSurf] LoRA adapter not found for {npcId}: {adapterPath}");
                return;
            }

            _adapterPaths[npcId] = adapterPath;
            var fileInfo = new FileInfo(adapterPath);
            float sizeMB = fileInfo.Length / (1024f * 1024f);
            Debug.Log($"[GameSurf] Registered LoRA adapter: {npcId} ({sizeMB:F1} MB)");
        }

        /// <summary>
        /// Register an adapter from an NpcProfile ScriptableObject.
        /// </summary>
        public void RegisterAdapter(NpcProfile profile)
        {
            if (profile == null) return;
            string path = profile.GetLoraAdapterFullPath();
            if (!string.IsNullOrEmpty(path))
                RegisterAdapter(profile.npcId, path);
        }

        /// <summary>
        /// Scan StreamingAssets/NpcModels/ for all available adapters.
        /// Expects: StreamingAssets/NpcModels/{npc_id}/adapter_model.gguf
        /// </summary>
        public int AutoDiscoverAdapters()
        {
            string modelsDir = Path.Combine(Application.streamingAssetsPath, "NpcModels");
            if (!Directory.Exists(modelsDir))
            {
                Debug.Log("[GameSurf] No NpcModels directory found in StreamingAssets");
                return 0;
            }

            int count = 0;
            foreach (string npcDir in Directory.GetDirectories(modelsDir))
            {
                string npcId = Path.GetFileName(npcDir);
                string adapterPath = Path.Combine(npcDir, "adapter_model.gguf");
                if (File.Exists(adapterPath))
                {
                    RegisterAdapter(npcId, adapterPath);
                    count++;
                }
            }

            Debug.Log($"[GameSurf] Auto-discovered {count} LoRA adapter(s)");
            return count;
        }

        /// <summary>
        /// Switch the active LoRA adapter to a different NPC.
        /// If the NPC has no registered adapter, switches to base model only.
        /// </summary>
        /// <returns>True if switch succeeded (or already active)</returns>
        public bool SwitchToNpc(string npcId)
        {
            if (!_model.IsLoaded)
            {
                Debug.LogError("[GameSurf] Cannot switch adapter — no model loaded");
                return false;
            }

            // Already active
            if (_activeNpcId == npcId)
            {
                Debug.Log($"[GameSurf] LoRA already active for {npcId}");
                return true;
            }

            // No adapter registered — use base model
            if (string.IsNullOrEmpty(npcId) || !_adapterPaths.TryGetValue(npcId, out string adapterPath))
            {
                _model.UnloadLoraAdapter();
                _activeNpcId = npcId;
                Debug.Log($"[GameSurf] Using base model for {npcId ?? "(none)"} (no LoRA adapter)");
                return true;
            }

            // Switch adapter
            bool success = _model.LoadLoraAdapter(adapterPath);
            if (success)
            {
                _activeNpcId = npcId;
                Debug.Log($"[GameSurf] Switched LoRA adapter to: {npcId}");
            }
            else
            {
                Debug.LogError($"[GameSurf] Failed to switch to {npcId} — remaining on {_activeNpcId ?? "base"}");
            }

            return success;
        }

        /// <summary>
        /// Switch back to base model only (no LoRA adapter).
        /// </summary>
        public void SwitchToBaseModel()
        {
            _model.UnloadLoraAdapter();
            _activeNpcId = null;
            Debug.Log("[GameSurf] Switched to base model (no LoRA)");
        }

        /// <summary>
        /// Check if an NPC has a registered LoRA adapter.
        /// </summary>
        public bool HasAdapter(string npcId)
        {
            return _adapterPaths.ContainsKey(npcId);
        }

        /// <summary>
        /// Get the adapter path for an NPC, or null.
        /// </summary>
        public string GetAdapterPath(string npcId)
        {
            return _adapterPaths.TryGetValue(npcId, out string path) ? path : null;
        }

        /// <summary>
        /// Get all registered NPC IDs.
        /// </summary>
        public IEnumerable<string> GetRegisteredNpcIds()
        {
            return _adapterPaths.Keys;
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                SwitchToBaseModel();
                _adapterPaths.Clear();
                _disposed = true;
            }
        }
    }
}
