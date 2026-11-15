package com.ai.codex;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class ConversationActivityTest {
    private static final String THREAD = "11111111-2222-7333-8444-555555555555";
    private static final String STORAGE = "aaaaaaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee";
    @Test public void recognizesLegacyAndSuffixedRolloutsWithoutChangingThreadIdentity() {
        assertEquals(THREAD, ConversationActivity.threadFromRollout("rollout-2026-11-15T00-08-37-" + THREAD + ".jsonl"));
        assertEquals(THREAD, ConversationActivity.threadFromRollout("rollout-2026-11-15T00-08-37-" + THREAD + "_" + STORAGE + ".jsonl"));
        assertNull(ConversationActivity.threadFromRollout("rollout-2026-11-15T00-08-37-" + THREAD + "_invalid.jsonl"));
        assertNull(ConversationActivity.threadFromRollout("../rollout-2026-11-15T00-08-37-" + THREAD + ".jsonl"));
    }
    @Test public void ordinaryExecWorkFromCurrentRolloutAppearsUntilMatchingCompletion() throws Exception {
        ConversationActivity state = new ConversationActivity();
        String thread = ConversationActivity.threadFromRollout("rollout-2026-11-15T00-08-37-" + THREAD + "_" + STORAGE + ".jsonl");
        state.accept(thread, event("task_started", "run"));
        JSONObject call = new JSONObject().put("type", "response_item").put("payload",
            new JSONObject().put("type", "custom_tool_call").put("name", "exec").put("input", "private command arguments"));
        assertEquals(ConversationActivity.Change.UPDATED, state.accept(thread, call));
        assertEquals(1, state.activeCount());
        assertEquals("正在执行命令", state.status(thread));
        JSONObject output = new JSONObject().put("type", "response_item").put("payload",
            new JSONObject().put("type", "custom_tool_call_output").put("output", "private output"));
        assertEquals(ConversationActivity.Change.UPDATED, state.accept(thread, output));
        assertEquals("正在整理结果", state.status(thread));
        assertEquals(ConversationActivity.Change.COMPLETED, state.accept(thread, event("task_complete", "run")));
        assertEquals(0, state.activeCount());
        assertEquals(ConversationActivity.Change.NONE, state.accept(thread, call));
    }
    @Test public void currentPersistedCompletionEventsUpdateProgressWithoutLegacyEvents() throws Exception {
        ConversationActivity state = new ConversationActivity();
        state.accept("a", event("task_started", "run"));
        JSONObject completed = event("item_completed", "run");
        completed.getJSONObject("payload").put("item", new JSONObject().put("type", "CommandExecution").put("command", "secret"));
        assertEquals(ConversationActivity.Change.UPDATED, state.accept("a", completed));
        assertEquals("正在整理结果", state.status("a"));
        completed.getJSONObject("payload").put("item", new JSONObject().put("type", "Reasoning").put("raw_content", "private"));
        state.accept("a", completed);
        assertEquals("正在思考", state.status("a"));
    }
    @Test public void responsesAndUserMessagesCannotCreateOrReviveAnUnobservedTask() throws Exception {
        ConversationActivity state = new ConversationActivity();
        JSONObject response = new JSONObject().put("type", "response_item").put("payload",
            new JSONObject().put("type", "function_call").put("name", "apply_patch"));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", response));
        state.accept("a", event("task_started", "new"));
        response.getJSONObject("payload").put("turn_id", "old");
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", response));
        response.put("payload", new JSONObject().put("type", "message").put("role", "user"));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", response));
        assertEquals("正在思考", state.status("a"));
    }
    private JSONObject event(String type, String turn) throws Exception {
        return new JSONObject().put("type", "event_msg").put("payload", new JSONObject().put("type", type).put("turn_id", turn));
    }
    @Test public void completionRequiresObservedMatchingStart() throws Exception {
        ConversationActivity state = new ConversationActivity();
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("task_complete", "t1")));
        assertEquals(ConversationActivity.Change.STARTED, state.accept("a", event("task_started", "t1")));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("task_complete", "old")));
        assertEquals(1, state.activeCount());
        assertEquals(ConversationActivity.Change.COMPLETED, state.accept("a", event("task_complete", "t1")));
        assertEquals(0, state.activeCount());
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("task_complete", "t1")));
    }
    @Test public void concurrentConversationsAndDuplicateStarts() throws Exception {
        ConversationActivity state = new ConversationActivity();
        state.accept("a", event("task_started", "t1"));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("task_started", "t1")));
        state.accept("b", event("task_started", "t2"));
        assertEquals(2, state.activeCount());
        state.accept("a", event("task_complete", "t1"));
        assertEquals(1, state.activeCount());
        assertEquals(ConversationActivity.Change.INTERRUPTED, state.accept("b", event("turn_aborted", "t2")));
        assertEquals(0, state.activeCount());
    }
    @Test public void replacementTurnDoesNotCompleteOnOldEvent() throws Exception {
        ConversationActivity state = new ConversationActivity();
        state.accept("a", event("task_started", "t1"));
        state.accept("a", event("task_started", "t2"));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("turn_aborted", "t1")));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("task_complete", "")));
        assertEquals(1, state.activeCount());
    }
    @Test public void progressOnlyBelongsToAnObservedCurrentTurn() throws Exception {
        ConversationActivity state = new ConversationActivity();
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("exec_command_begin", "t1")));
        state.accept("a", event("task_started", "t1"));
        assertEquals(ConversationActivity.Change.UPDATED, state.accept("a", event("exec_command_begin", "t1")));
        assertEquals("正在执行命令", state.status("a"));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("exec_command_begin", "t1")));
        state.accept("a", event("task_started", "t2"));
        assertEquals(ConversationActivity.Change.NONE, state.accept("a", event("patch_apply_begin", "t1")));
        assertEquals("正在思考", state.status("a"));
    }
    @Test public void phoneProgressDoesNotExposeArgumentsOrAffectAnotherConversation() throws Exception {
        ConversationActivity state = new ConversationActivity();
        state.accept("a", event("task_started", "ta"));
        state.accept("b", event("task_started", "tb"));
        JSONObject message = event("mcp_tool_call_begin", "ta");
        message.getJSONObject("payload").put("invocation", new JSONObject().put("server", "phone")
            .put("arguments", new JSONObject().put("text", "private text")));
        assertEquals(ConversationActivity.Change.UPDATED, state.accept("a", message));
        assertEquals("正在操控手机", state.status("a"));
        assertEquals("正在思考", state.status("b"));
        state.accept("a", event("task_complete", "ta"));
        assertEquals(1, state.activeCount());
        assertEquals("正在思考", state.status("a"));
    }
}
