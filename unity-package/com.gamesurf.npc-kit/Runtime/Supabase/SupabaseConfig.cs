using UnityEngine;

namespace GameSurf.NpcKit
{
    [CreateAssetMenu(fileName = "SupabaseConfig", menuName = "GameSurf/Supabase Config", order = 2)]
    public class SupabaseConfig : ScriptableObject
    {
        [Header("Connection")]
        [Tooltip("Supabase project URL")]
        public string url = "http://127.0.0.1:16433";

        [Tooltip("Supabase anon/public key")]
        public string anonKey;

        [Tooltip("Service role key (dev only)")]
        public string serviceRoleKey;

        [Header("Options")]
        public bool useServiceRoleKey = false;
        public float timeoutSeconds = 30f;

        public string ActiveKey => useServiceRoleKey ? serviceRoleKey : anonKey;
        public string RestUrl => $"{url.TrimEnd('/')}/rest/v1";
        public string FunctionsUrl => $"{url.TrimEnd('/')}/functions/v1";
    }
}
