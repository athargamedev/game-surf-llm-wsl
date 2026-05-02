// GameSurf NPC Kit — LlamaCppBinding.cs
// P/Invoke wrapper for llama.cpp native library.
// Provides minimal API surface for GGUF model loading, LoRA adapter
// application, and text generation needed by the NPC dialogue system.
//
// Requires: libllama.so / llama.dll / libllama.dylib in Plugins/

using System;
using System.Runtime.InteropServices;
using System.Text;
using UnityEngine;

namespace GameSurf.NpcKit
{
    /// <summary>
    /// Low-level P/Invoke bindings for llama.cpp.
    /// These map to the llama.h C API.
    /// </summary>
    public static class LlamaCppNative
    {
#if UNITY_EDITOR_WIN || UNITY_STANDALONE_WIN
        private const string LibName = "llama";
#elif UNITY_EDITOR_OSX || UNITY_STANDALONE_OSX
        private const string LibName = "libllama";
#else
        private const string LibName = "libllama";
#endif

        // ── Initialization ───────────────────────────────────────────────────

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void llama_backend_init();

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void llama_backend_free();

        // ── Model loading ────────────────────────────────────────────────────

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr llama_model_load_from_file(
            [MarshalAs(UnmanagedType.LPUTF8Str)] string path_model,
            LlamaModelParams @params);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void llama_model_free(IntPtr model);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern LlamaModelParams llama_model_default_params();

        // ── Context ──────────────────────────────────────────────────────────

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr llama_init_from_model(
            IntPtr model,
            LlamaContextParams @params);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void llama_free(IntPtr ctx);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern LlamaContextParams llama_context_default_params();

        // ── LoRA adapters ────────────────────────────────────────────────────

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr llama_adapter_lora_init(
            IntPtr model,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string path_lora);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_set_adapter_lora(
            IntPtr ctx,
            IntPtr adapter,
            float scale);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_rm_adapter_lora(
            IntPtr ctx,
            IntPtr adapter);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void llama_adapter_lora_free(IntPtr adapter);

        // ── Tokenization ─────────────────────────────────────────────────────

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_tokenize(
            IntPtr model,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string text,
            int text_len,
            int[] tokens,
            int n_tokens_max,
            [MarshalAs(UnmanagedType.I1)] bool add_special,
            [MarshalAs(UnmanagedType.I1)] bool parse_special);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_token_to_piece(
            IntPtr model,
            int token,
            byte[] buf,
            int length,
            int lstrip,
            [MarshalAs(UnmanagedType.I1)] bool special);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_token_eos(IntPtr model);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_token_bos(IntPtr model);

        // ── Vocab ────────────────────────────────────────────────────────────

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_n_vocab(IntPtr model);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int llama_n_ctx(IntPtr ctx);
    }

    // ── Parameter structs ────────────────────────────────────────────────────

    [StructLayout(LayoutKind.Sequential)]
    public struct LlamaModelParams
    {
        public int n_gpu_layers;
        public int split_mode;
        public int main_gpu;
        public float tensor_split; // simplified — real struct has float*
        public IntPtr progress_callback;
        public IntPtr progress_callback_user_data;
        public IntPtr kv_overrides;
        [MarshalAs(UnmanagedType.I1)] public bool vocab_only;
        [MarshalAs(UnmanagedType.I1)] public bool use_mmap;
        [MarshalAs(UnmanagedType.I1)] public bool use_mlock;
        [MarshalAs(UnmanagedType.I1)] public bool check_tensors;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct LlamaContextParams
    {
        public uint n_ctx;
        public uint n_batch;
        public uint n_ubatch;
        public uint n_seq_max;
        public int n_threads;
        public int n_threads_batch;
        // Additional fields omitted for brevity — use default params
    }

    /// <summary>
    /// High-level wrapper around the llama.cpp P/Invoke bindings.
    /// Manages model lifecycle, LoRA adapter loading, and text generation.
    /// </summary>
    public class LlamaCppModel : IDisposable
    {
        private IntPtr _model = IntPtr.Zero;
        private IntPtr _ctx = IntPtr.Zero;
        private IntPtr _activeAdapter = IntPtr.Zero;
        private string _activeAdapterPath;
        private bool _disposed;

        /// <summary>Whether a model is currently loaded.</summary>
        public bool IsLoaded => _model != IntPtr.Zero && _ctx != IntPtr.Zero;

        /// <summary>The currently active LoRA adapter path, or null.</summary>
        public string ActiveAdapterPath => _activeAdapterPath;

        /// <summary>
        /// Initialize the llama.cpp backend. Call once at application startup.
        /// </summary>
        public static void InitBackend()
        {
            try
            {
                LlamaCppNative.llama_backend_init();
                Debug.Log("[GameSurf] llama.cpp backend initialized");
            }
            catch (DllNotFoundException ex)
            {
                Debug.LogError($"[GameSurf] llama.cpp native library not found: {ex.Message}");
                Debug.LogError("[GameSurf] Place libllama.so/llama.dll in Plugins/ folder");
            }
        }

        /// <summary>
        /// Load a GGUF model from disk.
        /// </summary>
        /// <param name="modelPath">Absolute path to the .gguf file</param>
        /// <param name="nGpuLayers">Number of layers to offload to GPU (32 = all for 3B)</param>
        /// <param name="nCtx">Context window size in tokens</param>
        public bool LoadModel(string modelPath, int nGpuLayers = 32, uint nCtx = 2048)
        {
            if (IsLoaded)
            {
                Debug.LogWarning("[GameSurf] Model already loaded — unload first");
                return false;
            }

            try
            {
                var modelParams = LlamaCppNative.llama_model_default_params();
                modelParams.n_gpu_layers = nGpuLayers;
                modelParams.use_mmap = true;

                _model = LlamaCppNative.llama_model_load_from_file(modelPath, modelParams);
                if (_model == IntPtr.Zero)
                {
                    Debug.LogError($"[GameSurf] Failed to load model: {modelPath}");
                    return false;
                }

                var ctxParams = LlamaCppNative.llama_context_default_params();
                ctxParams.n_ctx = nCtx;

                _ctx = LlamaCppNative.llama_init_from_model(_model, ctxParams);
                if (_ctx == IntPtr.Zero)
                {
                    Debug.LogError("[GameSurf] Failed to create context");
                    LlamaCppNative.llama_model_free(_model);
                    _model = IntPtr.Zero;
                    return false;
                }

                Debug.Log($"[GameSurf] Model loaded: {modelPath} (GPU layers={nGpuLayers}, ctx={nCtx})");
                return true;
            }
            catch (Exception ex)
            {
                Debug.LogError($"[GameSurf] Model load exception: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Load and apply a LoRA adapter. Removes the previous adapter if one is active.
        /// </summary>
        /// <param name="adapterPath">Absolute path to the .gguf LoRA adapter</param>
        /// <param name="scale">LoRA scaling factor (default 1.0)</param>
        /// <returns>True if adapter was loaded successfully</returns>
        public bool LoadLoraAdapter(string adapterPath, float scale = 1.0f)
        {
            if (!IsLoaded)
            {
                Debug.LogError("[GameSurf] Cannot load LoRA — no model loaded");
                return false;
            }

            // Remove existing adapter
            if (_activeAdapter != IntPtr.Zero)
            {
                UnloadLoraAdapter();
            }

            try
            {
                _activeAdapter = LlamaCppNative.llama_adapter_lora_init(_model, adapterPath);
                if (_activeAdapter == IntPtr.Zero)
                {
                    Debug.LogError($"[GameSurf] Failed to load LoRA adapter: {adapterPath}");
                    return false;
                }

                int result = LlamaCppNative.llama_set_adapter_lora(_ctx, _activeAdapter, scale);
                if (result != 0)
                {
                    Debug.LogError($"[GameSurf] Failed to apply LoRA adapter (error={result})");
                    LlamaCppNative.llama_adapter_lora_free(_activeAdapter);
                    _activeAdapter = IntPtr.Zero;
                    return false;
                }

                _activeAdapterPath = adapterPath;
                Debug.Log($"[GameSurf] LoRA adapter loaded: {adapterPath} (scale={scale})");
                return true;
            }
            catch (Exception ex)
            {
                Debug.LogError($"[GameSurf] LoRA load exception: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Remove the currently active LoRA adapter.
        /// </summary>
        public void UnloadLoraAdapter()
        {
            if (_activeAdapter == IntPtr.Zero)
                return;

            try
            {
                LlamaCppNative.llama_rm_adapter_lora(_ctx, _activeAdapter);
                LlamaCppNative.llama_adapter_lora_free(_activeAdapter);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[GameSurf] LoRA unload warning: {ex.Message}");
            }

            _activeAdapter = IntPtr.Zero;
            _activeAdapterPath = null;
            Debug.Log("[GameSurf] LoRA adapter unloaded");
        }

        /// <summary>
        /// Tokenize a string into token IDs.
        /// </summary>
        public int[] Tokenize(string text, bool addSpecial = true)
        {
            if (_model == IntPtr.Zero) return Array.Empty<int>();

            // First pass: get required length
            int nTokens = LlamaCppNative.llama_tokenize(
                _model, text, text.Length, null, 0, addSpecial, true);

            if (nTokens < 0) nTokens = -nTokens; // returns negative count when buffer is too small

            var tokens = new int[nTokens + 1];
            int actual = LlamaCppNative.llama_tokenize(
                _model, text, text.Length, tokens, tokens.Length, addSpecial, true);

            if (actual < 0) actual = 0;
            var result = new int[actual];
            Array.Copy(tokens, result, actual);
            return result;
        }

        /// <summary>
        /// Convert a token ID back to its text piece.
        /// </summary>
        public string TokenToPiece(int token)
        {
            if (_model == IntPtr.Zero) return "";

            var buf = new byte[128];
            int len = LlamaCppNative.llama_token_to_piece(_model, token, buf, buf.Length, 0, false);
            if (len < 0) len = 0;
            return Encoding.UTF8.GetString(buf, 0, len);
        }

        /// <summary>Get the end-of-sequence token ID.</summary>
        public int EosToken => _model != IntPtr.Zero ? LlamaCppNative.llama_token_eos(_model) : -1;

        /// <summary>Get the beginning-of-sequence token ID.</summary>
        public int BosToken => _model != IntPtr.Zero ? LlamaCppNative.llama_token_bos(_model) : -1;

        /// <summary>Unload the model and free all resources.</summary>
        public void Unload()
        {
            UnloadLoraAdapter();

            if (_ctx != IntPtr.Zero)
            {
                LlamaCppNative.llama_free(_ctx);
                _ctx = IntPtr.Zero;
            }

            if (_model != IntPtr.Zero)
            {
                LlamaCppNative.llama_model_free(_model);
                _model = IntPtr.Zero;
            }

            Debug.Log("[GameSurf] Model unloaded");
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                Unload();
                _disposed = true;
            }
        }
    }
}
