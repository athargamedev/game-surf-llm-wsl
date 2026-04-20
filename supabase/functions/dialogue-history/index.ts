import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

interface HistoryRequest {
  player_id: string;
  npc_id: string;
  limit?: number;
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
      const { player_id, npc_id, limit = 50, session_id } = await req.json();

      if (!player_id || !npc_id) {
        return new Response(
          JSON.stringify({ success: false, error: "Missing player_id or npc_id" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      // Get sessions
      let sessionsQuery = supabase
        .from("dialogue_sessions")
        .select("session_id, status, started_at, ended_at, turn_count")
        .eq("player_id", player_id)
        .eq("npc_id", npc_id)
        .order("started_at", { ascending: false })
        .limit(limit);

      if (session_id) {
        sessionsQuery = sessionsQuery.eq("session_id", session_id);
      }

      const { data: sessions, error: sessionsError } = await sessionsQuery;

      if (sessionsError) {
        return new Response(
          JSON.stringify({ success: false, error: sessionsError.message }),
          { status: 500, headers: { "Content-Type": "application/json" } }
        );
      }

      if (!sessions || sessions.length === 0) {
        return new Response(
          JSON.stringify({ success: true, sessions: [], turns: [] }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Access-Control-Allow-Origin": "*",
            },
          }
        );
      }

      // Get turns for sessions
      const sessionIds = sessions.map((s) => s.session_id);
      const { data: turns, error: turnsError } = await supabase
        .from("dialogue_turns")
        .select("id, session_id, player_message, npc_response, created_at")
        .in("session_id", sessionIds)
        .order("created_at", { ascending: true });

      if (turnsError) {
        return new Response(
          JSON.stringify({ success: false, error: turnsError.message }),
          { status: 500, headers: { "Content-Type": "application/json" } }
        );
      }

      // Group turns by session
      const turnsBySession = (turns || []).reduce(
        (
          acc: Record<string, typeof turns>,
          turn: { session_id: string }
        ) => {
          if (!acc[turn.session_id]) {
            acc[turn.session_id] = [];
          }
          acc[turn.session_id].push(turn);
          return acc;
        },
        {}
      );

      return new Response(
        JSON.stringify({
          success: true,
          sessions: sessions.map((s) => ({
            ...s,
            turns: turnsBySession[s.session_id] || [],
          })),
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

    // GET request - return sessions list only
    if (req.method === "GET") {
      const url = new URL(req.url);
      const player_id = url.searchParams.get("player_id");
      const npc_id = url.searchParams.get("npc_id");
      const limit = parseInt(url.searchParams.get("limit") || "10");

      if (!player_id || !npc_id) {
        return new Response(
          JSON.stringify({ success: false, error: "Missing parameters" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      const { data: sessions, error } = await supabase
        .from("dialogue_sessions")
        .select("session_id, status, started_at, ended_at, turn_count")
        .eq("player_id", player_id)
        .eq("npc_id", npc_id)
        .order("started_at", { ascending: false })
        .limit(limit);

      return new Response(
        JSON.stringify({ success: true, sessions: sessions || [] }),
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