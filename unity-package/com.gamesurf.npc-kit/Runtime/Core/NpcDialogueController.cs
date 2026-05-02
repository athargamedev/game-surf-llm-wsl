// GameSurf NPC Kit — NpcDialogueController.cs
// Main MonoBehaviour that Unity developers attach to NPC GameObjects.
// Manages the dialogue lifecycle: session start → chat → session end.

using System;
using System.Collections;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Events;

namespace GameSurf.NpcKit
{
    /// <summary>
    /// Event fired when the NPC produces a response.
    /// </summary>
    [Serializable]
    public class NpcResponseEvent : UnityEvent<string> { }

    /// <summary>
    /// Event fired when a session starts, passing the session ID.
    /// </summary>
    [Serializable]
    public class SessionStartedEvent : UnityEvent<string> { }

    /// <summary>
    /// Main dialogue controller for an NPC. Attach to any GameObject with an NpcProfile.
    /// Handles session lifecycle, message routing, and memory integration.
    /// </summary>
    public class NpcDialogueController : MonoBehaviour
    {
        [Header("NPC Configuration")]
        [Tooltip("The NPC Profile ScriptableObject defining this character")]
        public NpcProfile profile;

        [Header("Inference Settings")]
        [Tooltip("Use a remote server instead of local llama.cpp inference")]
        public bool useRemoteServer = false;

        [Tooltip("Remote server URL (when useRemoteServer = true)")]
        public string remoteServerUrl = "http://127.0.0.1:8000";

        [Tooltip("Maximum tokens in NPC response")]
        public int maxResponseTokens = 64;

        [Tooltip("Temperature for response generation (0.0 = deterministic, 1.0 = creative)")]
        [Range(0f, 1f)]
        public float temperature = 0.35f;

        [Header("Memory")]
        [Tooltip("Enable Supabase memory persistence")]
        public bool enableMemory = true;

        [Tooltip("Supabase configuration for memory storage")]
        public SupabaseConfig supabaseConfig;

        [Header("Events")]
        public NpcResponseEvent onNpcResponse;
        public SessionStartedEvent onSessionStarted;
        public UnityEvent onSessionEnded;

        // Runtime state
        private string _currentSessionId;
        private string _currentPlayerId;
        private string _memoryContext;
        private bool _isProcessing;

        /// <summary>True while waiting for an NPC response.</summary>
        public bool IsProcessing => _isProcessing;

        /// <summary>Current active session ID, or null.</summary>
        public string CurrentSessionId => _currentSessionId;

        /// <summary>
        /// Start a dialogue session for a player with this NPC.
        /// Loads any prior memory context from Supabase.
        /// </summary>
        public async Task<string> StartSession(string playerId, string playerName = null)
        {
            if (profile == null)
            {
                Debug.LogError("[GameSurf] NpcDialogueController: No NpcProfile assigned!");
                return null;
            }

            _currentPlayerId = playerId;
            _memoryContext = null;

            if (enableMemory && supabaseConfig != null)
            {
                try
                {
                    var memoryManager = new NpcMemoryManager(supabaseConfig);
                    _memoryContext = await memoryManager.LoadPlayerContext(playerId, profile.npcId);

                    // Create session in Supabase
                    _currentSessionId = await memoryManager.CreateSession(playerId, profile.npcId);

                    // Upsert player profile if name provided
                    if (!string.IsNullOrEmpty(playerName))
                    {
                        await memoryManager.UpsertPlayerProfile(playerId, playerName);
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[GameSurf] Memory load failed, continuing without memory: {ex.Message}");
                }
            }

            if (string.IsNullOrEmpty(_currentSessionId))
            {
                _currentSessionId = Guid.NewGuid().ToString();
            }

            onSessionStarted?.Invoke(_currentSessionId);
            Debug.Log($"[GameSurf] Session started: {profile.displayName} (session={_currentSessionId.Substring(0, 8)})");

            return _currentSessionId;
        }

        /// <summary>
        /// Send a player message and get an NPC response.
        /// </summary>
        public async Task<string> SendMessage(string playerMessage)
        {
            if (_isProcessing)
            {
                Debug.LogWarning("[GameSurf] Already processing a message — ignoring.");
                return null;
            }

            if (profile == null)
            {
                Debug.LogError("[GameSurf] No NpcProfile assigned!");
                return null;
            }

            _isProcessing = true;

            try
            {
                string npcResponse;

                if (useRemoteServer)
                {
                    npcResponse = await SendMessageRemote(playerMessage);
                }
                else
                {
                    npcResponse = await SendMessageLocal(playerMessage);
                }

                // Clean the response
                npcResponse = ResponseCleaner.Clean(npcResponse);

                // Record turn in Supabase
                if (enableMemory && supabaseConfig != null && !string.IsNullOrEmpty(_currentSessionId))
                {
                    try
                    {
                        var memoryManager = new NpcMemoryManager(supabaseConfig);
                        await memoryManager.RecordTurn(_currentSessionId, playerMessage, npcResponse);
                    }
                    catch (Exception ex)
                    {
                        Debug.LogWarning($"[GameSurf] Failed to record turn: {ex.Message}");
                    }
                }

                onNpcResponse?.Invoke(npcResponse);
                return npcResponse;
            }
            finally
            {
                _isProcessing = false;
            }
        }

        /// <summary>
        /// End the current dialogue session and trigger memory summarization.
        /// </summary>
        public async Task EndSession()
        {
            if (string.IsNullOrEmpty(_currentSessionId))
                return;

            if (enableMemory && supabaseConfig != null)
            {
                try
                {
                    var memoryManager = new NpcMemoryManager(supabaseConfig);
                    await memoryManager.EndSession(_currentSessionId, _currentPlayerId, profile.npcId);
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[GameSurf] Failed to end session in Supabase: {ex.Message}");
                }
            }

            Debug.Log($"[GameSurf] Session ended: {profile.displayName} (session={_currentSessionId.Substring(0, 8)})");
            _currentSessionId = null;
            _currentPlayerId = null;
            _memoryContext = null;

            onSessionEnded?.Invoke();
        }

        // ── Private: Remote server mode ──────────────────────────────────────

        private async Task<string> SendMessageRemote(string playerMessage)
        {
            var payload = new ChatRequestPayload
            {
                player_id = _currentPlayerId,
                npc_id = profile.npcId,
                message = playerMessage,
                session_id = _currentSessionId,
            };

            string json = JsonUtility.ToJson(payload);

            using var www = new UnityEngine.Networking.UnityWebRequest(
                $"{remoteServerUrl}/chat", "POST");
            www.uploadHandler = new UnityEngine.Networking.UploadHandlerRaw(
                System.Text.Encoding.UTF8.GetBytes(json));
            www.downloadHandler = new UnityEngine.Networking.DownloadHandlerBuffer();
            www.SetRequestHeader("Content-Type", "application/json");

            var op = www.SendWebRequest();
            while (!op.isDone)
                await Task.Yield();

            if (www.result != UnityEngine.Networking.UnityWebRequest.Result.Success)
            {
                Debug.LogError($"[GameSurf] Remote chat failed: {www.error}");
                return "I need a moment to gather that thought. Please ask me again.";
            }

            var response = JsonUtility.FromJson<ChatResponsePayload>(www.downloadHandler.text);
            return response.npc_response;
        }

        // ── Private: Local inference mode (llama.cpp) ────────────────────────

        private async Task<string> SendMessageLocal(string playerMessage)
        {
            // Build system prompt with memory context
            string systemPrompt = profile.BuildSystemPrompt(_memoryContext);

            // TODO: Integrate LlamaCppBinding for local inference
            // For now, fall back to remote server with a warning
            Debug.LogWarning("[GameSurf] Local inference not yet implemented — falling back to remote server.");
            return await SendMessageRemote(playerMessage);
        }

        // ── Cleanup ──────────────────────────────────────────────────────────

        private async void OnDestroy()
        {
            if (!string.IsNullOrEmpty(_currentSessionId))
            {
                await EndSession();
            }
        }

        // ── Serializable payloads ────────────────────────────────────────────

        [Serializable]
        private class ChatRequestPayload
        {
            public string player_id;
            public string npc_id;
            public string message;
            public string session_id;
        }

        [Serializable]
        private class ChatResponsePayload
        {
            public string npc_response;
            public string session_id;
        }
    }
}
