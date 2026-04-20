import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

interface MemoryRequest {
  player_id: string;
  npc_id: string;
  session_id?: string;
}

interface MemoryResponse {
  success: boolean;
  summary?: string;
  session_count?: number;
  message: string;
}

serve(async (req: Request): Promise<Response> => {
  // Handle CORS
  if (req.method === "OPTIONS") {
    return new Response("ok", {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      },
    });
  }

  try {
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    if (req.method === "POST") {
      const body: MemoryRequest = await req.json();
      const { player_id, npc_id, session_id } = body;

      if (!player_id || !npc_id) {
        return new Response(
          JSON.stringify({
            success: false,
            message: "Missing player_id or npc_id",
          }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      // If session_id provided, trigger summarization
      if (session_id) {
        const { error } = await supabase.rpc("summarize_dialogue_session", {
          session_id_param: session_id,
          player_id_param: player_id,
          npc_id_param: npc_id,
        });

        if (error) {
          return new Response(
            JSON.stringify({
              success: false,
              message: `Summarization error: ${error.message}`,
            }),
            { status: 500, headers: { "Content-Type": "application/json" } }
          );
        }
      }

      // Retrieve the memory
      const { data, error } = await supabase.rpc("get_player_npc_memory", {
        player_id_param: player_id,
        npc_id_param: npc_id,
      });

      if (error) {
        return new Response(
          JSON.stringify({
            success: false,
            message: `Memory retrieval error: ${error.message}`,
          }),
          { status: 500, headers: { "Content-Type": "application/json" } }
        );
      }

      const memory = data?.[0];
      return new Response(
        JSON.stringify({
          success: true,
          summary: memory?.summary || null,
          session_count: memory?.session_count || 0,
          message: "Memory retrieved successfully",
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    } else if (req.method === "GET") {
      const url = new URL(req.url);
      const player_id = url.searchParams.get("player_id");
      const npc_id = url.searchParams.get("npc_id");

      if (!player_id || !npc_id) {
        return new Response(
          JSON.stringify({
            success: false,
            message: "Missing player_id or npc_id query parameters",
          }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      const { data, error } = await supabase.rpc("get_player_npc_memory", {
        player_id_param: player_id,
        npc_id_param: npc_id,
      });

      if (error) {
        return new Response(
          JSON.stringify({
            success: false,
            message: `Memory retrieval error: ${error.message}`,
          }),
          { status: 500, headers: { "Content-Type": "application/json" } }
        );
      }

      const memory = data?.[0];
      return new Response(
        JSON.stringify({
          success: true,
          data: memory || null,
          message: "Memory retrieved successfully",
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
      JSON.stringify({ success: false, message: "Method not allowed" }),
      { status: 405, headers: { "Content-Type": "application/json" } }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({
        success: false,
        message: `Server error: ${err.message}`,
      }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
});
