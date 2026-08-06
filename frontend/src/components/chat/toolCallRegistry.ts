import type { Component } from 'vue';
import type { z } from 'zod';
import type { ToolCallPayload } from 'src/utils/model';
import ExpertAnswerToolCall from './ExpertAnswerToolCall.vue';
import GenericToolCall from './GenericToolCall.vue';
import HumanitarianContextToolCall from './HumanitarianContextToolCall.vue';
import RecallEventsToolCall from './RecallEventsToolCall.vue';
import RecordEventToolCall from './RecordEventToolCall.vue';
import {
    baseToolCallPayloadSchema,
    expertAnswerToolCallPayloadSchema,
    humanitarianContextToolCallPayloadSchema,
    recallEventsToolCallPayloadSchema,
    recordEventToolCallPayloadSchema,
} from './toolCallSchemas';

interface ToolCallRegistration {
    component: Component;
    inputSchema: z.ZodType;
}

interface ResolvedToolCall {
    component: Component;
    payload: unknown;
}

function defineToolCall<Schema extends z.ZodType>(
    component: Component<{ payload: z.output<Schema> }>,
    inputSchema: Schema,
): ToolCallRegistration {
    return { component, inputSchema };
}

const TOOL_CALL_REGISTRY: Record<string, ToolCallRegistration> = {
    ask_meditron: defineToolCall(ExpertAnswerToolCall, expertAnswerToolCallPayloadSchema),
    ask_legitron: defineToolCall(ExpertAnswerToolCall, expertAnswerToolCallPayloadSchema),
    get_humanitarian_context: defineToolCall(
        HumanitarianContextToolCall,
        humanitarianContextToolCallPayloadSchema,
    ),
    record_event: defineToolCall(RecordEventToolCall, recordEventToolCallPayloadSchema),
    recall_events: defineToolCall(RecallEventsToolCall, recallEventsToolCallPayloadSchema),
};

export function resolveToolCall(payload: ToolCallPayload | null): ResolvedToolCall {
    const basePayload = baseToolCallPayloadSchema.safeParse(payload);
    if (!basePayload.success) {
        return { component: GenericToolCall, payload: null };
    }

    const registration = TOOL_CALL_REGISTRY[basePayload.data.tool_name];
    if (!registration) {
        return { component: GenericToolCall, payload: basePayload.data };
    }

    const parsedPayload = registration.inputSchema.safeParse(payload);
    if (!parsedPayload.success) {
        return { component: GenericToolCall, payload: basePayload.data };
    }

    return { component: registration.component, payload: parsedPayload.data };
}
