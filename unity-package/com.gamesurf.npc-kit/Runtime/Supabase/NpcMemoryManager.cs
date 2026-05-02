// GameSurf NPC Kit — NpcMemoryManager.cs
// Lightweight REST client for Supabase memory operations.
// Ported from scripts/supabase_client.py SupabaseClient class.

using System;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace GameSurf.NpcKit
{
    /// <summary>
    /// Manages NPC memory persistence via Supabase REST API.
    /// Ported from Python: scripts/supabase_client.py
    /// </summary>
    public class NpcMemoryManager
    {
        private readonly SupabaseConfig _config;

        public NpcMemoryManager(SupabaseConfig config)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
        }

        /// <summary>Load prior memory context for a player+NPC pair.</summary>
        public async Task<string> LoadPlayerContext(string playerId, string npcId)
        {
            string url = $"{_config.RestUrl}/npc_memories" +
                          $"?player_id=eq.{playerId}&npc_id=eq.{npcId}" +
                          "&order=created_at.desc&limit=3&select=summary";
            string json = await Get(url);
            if (string.IsNullOrEmpty(json) || json == "[]")
                return null;
            return json; // Caller parses
        }

        /// <summary>Create a new dialogue session.</summary>
        public async Task<string> CreateSession(string playerId, string npcId)
        {
            string body = JsonUtility.ToJson(new SessionInsert
            {
                player_id = playerId,
                npc_id = npcId,
                status = "active"
            });
            string resp = await Post($"{_config.RestUrl}/dialogue_sessions?select=session_id", body);
            if (!string.IsNullOrEmpty(resp))
            {
                var parsed = JsonUtility.FromJson<SessionIdWrapper>($"{{\"items\":{resp}}}");
                // Simple extraction — UnityWebRequest JSON support is limited
                int idx = resp.IndexOf("session_id", StringComparison.Ordinal);
                if (idx > 0)
                {
                    int start = resp.IndexOf('"', idx + 13) + 1;
                    int end = resp.IndexOf('"', start);
                    if (start > 0 && end > start)
                        return resp.Substring(start, end - start);
                }
            }
            return Guid.NewGuid().ToString();
        }

        /// <summary>Record a dialogue turn.</summary>
        public async Task RecordTurn(string sessionId, string playerMsg, string npcResponse)
        {
            string body = JsonUtility.ToJson(new TurnInsert
            {
                session_id = sessionId,
                player_message = playerMsg,
                npc_response = npcResponse
            });
            await Post($"{_config.RestUrl}/dialogue_turns", body);
        }

        /// <summary>End a session.</summary>
        public async Task EndSession(string sessionId, string playerId, string npcId)
        {
            string body = "{\"status\":\"ended\",\"ended_at\":\"" + DateTime.UtcNow.ToString("o") + "\"}";
            await Patch($"{_config.RestUrl}/dialogue_sessions?session_id=eq.{sessionId}", body);
        }

        /// <summary>Create or update player profile.</summary>
        public async Task UpsertPlayerProfile(string playerId, string displayName)
        {
            string body = JsonUtility.ToJson(new PlayerProfileUpsert
            {
                player_id = playerId,
                display_name = displayName
            });
            string url = $"{_config.RestUrl}/player_profiles";
            await Post(url + "?on_conflict=player_id", body, prefer: "resolution=merge-duplicates");
        }

        // ── HTTP helpers ─────────────────────────────────────────────────────

        private async Task<string> Get(string url)
        {
            using var req = UnityWebRequest.Get(url);
            SetHeaders(req);
            var op = req.SendWebRequest();
            while (!op.isDone) await Task.Yield();
            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogWarning($"[GameSurf] GET {url} failed: {req.error}");
                return null;
            }
            return req.downloadHandler.text;
        }

        private async Task<string> Post(string url, string jsonBody, string prefer = "return=representation")
        {
            using var req = new UnityWebRequest(url, "POST");
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(jsonBody));
            req.downloadHandler = new DownloadHandlerBuffer();
            SetHeaders(req);
            req.SetRequestHeader("Prefer", prefer);
            var op = req.SendWebRequest();
            while (!op.isDone) await Task.Yield();
            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogWarning($"[GameSurf] POST {url} failed: {req.error}");
                return null;
            }
            return req.downloadHandler.text;
        }

        private async Task Patch(string url, string jsonBody)
        {
            using var req = new UnityWebRequest(url, "PATCH");
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(jsonBody));
            req.downloadHandler = new DownloadHandlerBuffer();
            SetHeaders(req);
            var op = req.SendWebRequest();
            while (!op.isDone) await Task.Yield();
            if (req.result != UnityWebRequest.Result.Success)
                Debug.LogWarning($"[GameSurf] PATCH {url} failed: {req.error}");
        }

        private void SetHeaders(UnityWebRequest req)
        {
            req.SetRequestHeader("apikey", _config.ActiveKey);
            req.SetRequestHeader("Authorization", $"Bearer {_config.ActiveKey}");
            req.SetRequestHeader("Content-Type", "application/json");
        }

        // ── Serialization helpers ────────────────────────────────────────────

        [Serializable] private class SessionInsert { public string player_id; public string npc_id; public string status; }
        [Serializable] private class TurnInsert { public string session_id; public string player_message; public string npc_response; }
        [Serializable] private class PlayerProfileUpsert { public string player_id; public string display_name; }
        [Serializable] private class SessionIdWrapper { public string[] items; }
    }
}
