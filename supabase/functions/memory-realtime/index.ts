import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { createClient as createRealtimeClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

interface MemoryRequest {
  player_id: string;
  npc_id: string;
  action?: "get" | "update" | "search" | "sync";
  summary?: string;
  query?: string;
  session_id?: string;
}

serve(async (req: Request): Promise<Response> => {
  if (req.method === "OPTIONS") {
    return new Response("ok", {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      },
    });
  }

  const supabase = createClient(supabaseUrl, supabaseServiceKey);

  try {
    if (req.method === "POST") {
      const body: MemoryRequest = await req.json();
      const { player_id, npc_id, action = "get", summary, query, session_id } = body;

      if (!player_id || !npc_id) {
        return new Response(
          JSON.stringify({ success: false, error: "Missing player_id or npc_id" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      // GET memory context
      if (action === "get") {
        const { data, error } = await supabase.rpc("get_memory_context", {
          target_player_id: player_id,
          target_npc_id: npc_id,
          memory_limit: 5,
        });

        if (error) {
          return new Response(
            JSON.stringify({ success: false, error: error.message }),
            { status: 500, headers: { "Content-Type": "application/json" } }
          );
        }

        return new Response(
          JSON.stringify({
            success: true,
            memory: data?.[0] || null,
            action: "get",
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Access-Control-Allow-Origin": "*",
            },
          }
        );
      }

      // UPDATE/SYNC memory - summarize session and update
      if (action === "update" || action === "sync") {
        if (!session_id) {
          return new Response(
            JSON.stringify({ success: false, error: "session_id required for update" }),
            { status: 400, headers: { "Content-Type": "application/json" } }
          );
        }

        // Summarize the dialogue session
        const { error: summarizeError } = await supabase.rpc(
          "summarize_dialogue_session",
          {
            session_id_param: session_id,
            player_id_param: player_id,
            npc_id_param: npc_id,
          }
        );

        if (summarizeError) {
          console.error("Summarize error:", summarizeError);
        }

        // Also update session status to 'ended'
        await supabase
          .from("dialogue_sessions")
          .update({
            status: "ended",
            ended_at: new Date().toISOString(),
          })
          .eq("session_id", session_id);

        // Trigger async embedding queue
        await supabase.rpc("enqueue_memory_embedding", {
          p_session_id: session_id,
          p_player_id: player_id,
          p_npc_id: npc_id,
        });

        // Get updated memory context
        const { data: memory } = await supabase.rpc("get_memory_context", {
          target_player_id: player_id,
          target_npc_id: npc_id,
          memory_limit: 3,
        });

        return new Response(
          JSON.stringify({
            success: true,
            memory: memory?.[0] || null,
            action: "synced",
            message: "Memory summarized and synced",
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Access-Control-Allow-Origin": "*",
            },
          }
        );
      }

      // SEARCH semantic memories
      if (action === "search") {
        // This would require an embedding - simplified version
        const { data: memories, error } = await supabase
          .from("npc_memories")
          .select("memory_id, summary, memory_type, created_at")
          .eq("player_id", player_id)
          .eq("npc_id", npc_id)
          .order("created_at", { ascending: false })
          .limit(10);

        return new Response(
          JSON.stringify({
            success: true,
            memories: memories || [],
            action: "search",
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Access-Control-Allow-Origin": "*",
            },
          }
        );
      }

      return new Response(
        JSON.stringify({ success: false, error: "Unknown action" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // GET - Quick memory retrieval for NPC
    if (req.method === "GET") {
      const url = new URL(req.url);
      const player_id = url.searchParams.get("player_id");
      const npc_id = url.searchParams.get("npc_id");

      if (!player_id || !npc_id) {
        return new Response(
          JSON.stringify({ success: false, error: "Missing parameters" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      const { data: memory, error } = await supabase.rpc("get_memory_context", {
        target_player_id: player_id,
        target_npc_id: npc_id,
        memory_limit: 3,
      });

      if (error) {
        return new Response(
          JSON.stringify({ success: false, error: error.message }),
          { status: 500, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          success: true,
          memory: memory?.[0] || null,
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    return new Response(
      JSON.stringify({ success: false, error: "Method not allowed" }),
      { status: 405, headers: { "Content-Type": "application/json" } }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ success: false, error: err.message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
});