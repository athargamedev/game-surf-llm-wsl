import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

interface NPCRequest {
  npc_id?: string;
  is_active?: boolean;
  with_player_stats?: boolean;
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
    // GET - List NPCs or get specific NPC
    if (req.method === "GET") {
      const url = new URL(req.url);
      const npc_id = url.searchParams.get("npc_id");
      const with_stats = url.searchParams.get("with_player_stats") === "true";

      if (npc_id) {
        // Get specific NPC profile
        const { data: npc, error } = await supabase.rpc("get_npc_profile", {
          target_npc_id: npc_id,
        });

        if (error || !npc || npc.length === 0) {
          return new Response(
            JSON.stringify({ success: false, error: "NPC not found" }),
            { status: 404, headers: { "Content-Type": "application/json" } }
          );
        }

        let response = { success: true, npc: npc[0] };

        // Optionally add player stats
        if (with_stats) {
          const { data: stats } = await supabase.rpc("get_player_npc_stats", {
            target_player_id: "default",
            target_npc_id: npc_id,
          });
          if (stats && stats.length > 0) {
            response = { ...response, stats: stats[0] };
          }
        }

        return new Response(JSON.stringify(response), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        });
      }

      // List all active NPCs
      const { data: npcs, error } = await supabase
        .from("npc_profiles")
        .select("npc_id, display_name, npc_scope, subject, subject_focus, is_active, updated_at")
        .eq("is_active", true)
        .order("display_name");

      return new Response(
        JSON.stringify({ success: true, npcs: npcs || [] }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    // POST - Upsert NPC profile
    if (req.method === "POST") {
      const body = await req.json();
      const {
        npc_id,
        display_name,
        npc_scope = "instructor",
        artifact_key,
        subject,
        subject_focus,
        personality = {},
        voice_rules = [],
      } = body;

      if (!npc_id || !display_name || !subject) {
        return new Response(
          JSON.stringify({ success: false, error: "Missing required fields" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      const { error } = await supabase.rpc("upsert_npc_profile", {
        p_npc_id: npc_id,
        p_display_name: display_name,
        p_npc_scope: npc_scope,
        p_artifact_key: artifact_key,
        p_subject: subject,
        p_subject_focus: subject_focus,
        p_personality: personality,
        p_voice_rules: voice_rules,
      });

      if (error) {
        return new Response(
          JSON.stringify({ success: false, error: error.message }),
          { status: 500, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({ success: true, message: "NPC profile updated" }),
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